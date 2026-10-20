from cs_agent.cache.store import ChatSessionStore


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
