from cs_agent.cache.store import (
    ChatSessionStore,
    MemoryKV,
    allow,
    cache_key,
    get_kv,
    seconds_to_next_window,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_memory_session_keeps_recent_messages_until_ttl() -> None:
    clock = Clock()
    store = ChatSessionStore(ttl_s=60, max_messages=3, clock=clock)

    store.append("s1", "hi", "hello")
    store.append("s1", "spec?", "here")

    assert store.history("s1") == ["hello", "spec?", "here"]  # 최근 3개
    assert store.history("other") == []

    clock.now = 59
    store.append("s1", "thanks")  # 대화가 이어지면 TTL 이 다시 시작된다
    clock.now = 100
    assert store.history("s1") == ["spec?", "here", "thanks"]
    clock.now = 200
    assert store.history("s1") == []


class FakeRedis:
    """ChatSessionStore 가 쓰는 명령만 흉내 낸다."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.ttl: dict[str, int] = {}

    def lrange(self, key, start, end):
        return list(self.lists.get(key, []))

    def pipeline(self):
        return self

    def rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(values)

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists[key][start:]

    def expire(self, key, seconds):
        self.ttl[key] = seconds

    def execute(self):
        return None


def test_redis_session_trims_and_sets_ttl() -> None:
    redis = FakeRedis()
    store = ChatSessionStore(redis, ttl_s=3600, max_messages=2)

    store.append("s1", "안녕하세요", "hi")
    store.append("s1", "spec?")

    assert store.history("s1") == ["hi", "spec?"]
    assert redis.ttl["chat:s1"] == 3600


# --- MemoryKV · cache_key · allow (CSA-45) --------------------------------------------------


def test_memory_kv_expires_and_incr_keeps_ttl() -> None:
    clock = Clock()
    kv = MemoryKV(clock=clock)

    kv.set("a", "1", ex=10)
    assert kv.get("a") == "1" and kv.get("nope") is None
    assert kv.incr("n") == 1 and kv.incr("n") == 2
    assert kv.expire("n", 5) and not kv.expire("nope", 5)

    clock.now = 6
    assert kv.incr("n") == 1  # 만료돼서 다시 센다
    clock.now = 10
    assert kv.get("a") is None


def test_get_kv_falls_back_to_memory() -> None:
    assert isinstance(get_kv(""), MemoryKV)
    assert isinstance(get_kv("redis://127.0.0.1:1/0"), MemoryKV)  # 붙지 않으면 메모리


def test_cache_key_depends_on_task_and_prompt() -> None:
    key = cache_key("classify", "hello")
    assert key.startswith("llm:classify:")
    assert key == cache_key("classify", "hello")
    assert key != cache_key("classify", "hello!")
    assert key != cache_key("draft", "hello")


def test_allow_is_fixed_window_per_bucket() -> None:
    kv = MemoryKV()

    assert [allow("gemini", 2, 60, kv=kv, now=0) for _ in range(3)] == [True, True, False]
    assert allow("jev", 2, 60, kv=kv, now=1)  # 버킷마다 따로
    assert allow("gemini", 2, 60, kv=kv, now=60)  # 다음 창
    assert allow("gemini", 0, 60, kv=kv, now=0)  # 0 이면 제한 없음
    assert seconds_to_next_window(60, now=125) == 55


def test_allow_sets_window_ttl_on_redis() -> None:
    class CountingRedis:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}
            self.ttl: dict[str, int] = {}

        def incr(self, key):
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        def expire(self, key, seconds):
            self.ttl[key] = seconds

    redis = CountingRedis()
    assert allow("gemini", 1, 60, kv=redis, now=125)
    assert not allow("gemini", 1, 60, kv=redis, now=126)
    assert redis.ttl == {"rate:gemini:2": 61}
