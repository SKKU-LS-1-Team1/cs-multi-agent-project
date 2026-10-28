// 온보딩 화면 문구. 번역이 없는 키는 영어로 대체한다.
// 온보딩 외 화면(홈·상담·문의 등)은 아직 한국어 단일이라 이 구조에 연결돼 있지 않다.
const en = {
  tagline: 'Global Customer Support',
  title: 'Welcome',
  sub: 'Choose your language to get started.',
  country: 'Your country',
  detecting: 'Detecting your country…',
  unknown: 'Country unavailable',
  language: 'Language',
  start: 'Continue',
  selected: 'selected',
}
const T = {
  en,
  ja: { tagline: 'グローバルカスタマーサポート', title: 'ようこそ', sub: '言語を選んで始めましょう。', country: 'お住まいの国', detecting: '国を確認しています…', unknown: '国を確認できません', language: '言語', start: '続ける', selected: '選択中' },
  zh: { tagline: '全球客户支持', title: '欢迎', sub: '请选择语言开始使用。', country: '您所在的国家', detecting: '正在确认国家…', unknown: '无法确认国家', language: '语言', start: '继续', selected: '已选择' },
  es: { tagline: 'Atención al cliente global', title: 'Bienvenido', sub: 'Elija su idioma para comenzar.', country: 'Su país', detecting: 'Detectando su país…', unknown: 'País no disponible', language: 'Idioma', start: 'Continuar', selected: 'seleccionado' },
  pt: { tagline: 'Suporte global ao cliente', title: 'Bem-vindo', sub: 'Escolha seu idioma para começar.', country: 'Seu país', detecting: 'Detectando seu país…', unknown: 'País indisponível', language: 'Idioma', start: 'Continuar', selected: 'selecionado' },
  fr: { tagline: 'Support client mondial', title: 'Bienvenue', sub: 'Choisissez votre langue pour commencer.', country: 'Votre pays', detecting: 'Détection du pays…', unknown: 'Pays indisponible', language: 'Langue', start: 'Continuer', selected: 'sélectionné' },
  de: { tagline: 'Globaler Kundensupport', title: 'Willkommen', sub: 'Wählen Sie Ihre Sprache, um zu beginnen.', country: 'Ihr Land', detecting: 'Land wird erkannt…', unknown: 'Land nicht verfügbar', language: 'Sprache', start: 'Weiter', selected: 'ausgewählt' },
  it: { tagline: 'Assistenza clienti globale', title: 'Benvenuto', sub: 'Scegli la tua lingua per iniziare.', country: 'Il tuo paese', detecting: 'Rilevamento del paese…', unknown: 'Paese non disponibile', language: 'Lingua', start: 'Continua', selected: 'selezionato' },
  ar: { tagline: 'دعم العملاء العالمي', title: 'مرحبًا', sub: 'اختر لغتك للبدء.', country: 'بلدك', detecting: 'جارٍ تحديد البلد…', unknown: 'تعذّر تحديد البلد', language: 'اللغة', start: 'متابعة', selected: 'محدد' },
  ru: { tagline: 'Глобальная поддержка клиентов', title: 'Добро пожаловать', sub: 'Выберите язык, чтобы начать.', country: 'Ваша страна', detecting: 'Определяем страну…', unknown: 'Страна не определена', language: 'Язык', start: 'Продолжить', selected: 'выбрано' },
  th: { tagline: 'ฝ่ายสนับสนุนลูกค้าทั่วโลก', title: 'ยินดีต้อนรับ', sub: 'เลือกภาษาเพื่อเริ่มต้น', country: 'ประเทศของคุณ', detecting: 'กำลังตรวจสอบประเทศ…', unknown: 'ไม่สามารถระบุประเทศได้', language: 'ภาษา', start: 'ดำเนินการต่อ', selected: 'เลือกแล้ว' },
  id: { tagline: 'Dukungan Pelanggan Global', title: 'Selamat datang', sub: 'Pilih bahasa Anda untuk memulai.', country: 'Negara Anda', detecting: 'Mendeteksi negara…', unknown: 'Negara tidak tersedia', language: 'Bahasa', start: 'Lanjutkan', selected: 'dipilih' },
  vi: { tagline: 'Hỗ trợ khách hàng toàn cầu', title: 'Chào mừng', sub: 'Chọn ngôn ngữ để bắt đầu.', country: 'Quốc gia của bạn', detecting: 'Đang xác định quốc gia…', unknown: 'Không xác định được quốc gia', language: 'Ngôn ngữ', start: 'Tiếp tục', selected: 'đã chọn' },
  tr: { tagline: 'Küresel Müşteri Desteği', title: 'Hoş geldiniz', sub: 'Başlamak için dilinizi seçin.', country: 'Ülkeniz', detecting: 'Ülke algılanıyor…', unknown: 'Ülke doğrulanamadı', language: 'Dil', start: 'Devam', selected: 'seçildi' },
  pl: { tagline: 'Globalna obsługa klienta', title: 'Witamy', sub: 'Wybierz język, aby rozpocząć.', country: 'Twój kraj', detecting: 'Wykrywanie kraju…', unknown: 'Kraj niedostępny', language: 'Język', start: 'Dalej', selected: 'wybrano' },
}
export const t = (lang, key) => T[lang]?.[key] ?? en[key]
