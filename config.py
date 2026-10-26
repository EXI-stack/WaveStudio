
DEFAULT_PARAMS = {
    "preset_idx": 1,
    "wave_type": "linear",
    "mode": 0,
    "wave_width": 1350,
    "max_height": 420,
    "num_bars": 61,
    "bar_thickness": 10,
    "roundness": 100,
    "smoothing": 65,
    "sensitivity": 100,
    "color1": "#FFFFFF",
    "color2": "#A29BFE",
}

SUPPORTED_MEDIA_EXTENSIONS = (
    ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus",
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".3gp"
)

MODE_DESCRIPTIONS = [
    ("Live — реакция на текущий звук", "Симметричная живая пульсация полос в реальном времени в такт биту и частотам."),
    ("Progress — отображение прогресса трека", "Отображает форму всей аудиодорожки и закрашивает пройденную часть по мере проигрывания."),
    ("Scroll — бегущая дорожка", "Окно звуковой волны плавно движется слева направо синхронно с таймлайном."),
    ("Spectrum — классический спектр", "Классический частотный анализатор: басы и бочка слева, средние по центру, высокие справа."),
]

WAVE_PRESETS = [
    {
        "name": "1. Тонкие линии (Минимализм)",
        "wave_type": "linear", "num_bars": 95, "bar_thickness": 3,
        "roundness": 0, "wave_width": 1450, "max_height": 360
    },
    {
        "name": "2. Ритмичные волны (Пакеты волн)",
        "wave_type": "linear", "num_bars": 61, "bar_thickness": 10,
        "roundness": 100, "wave_width": 1350, "max_height": 440
    },
    {
        "name": "3. Широкие блоки (Крупные полосы)",
        "wave_type": "linear", "num_bars": 23, "bar_thickness": 34,
        "roundness": 25, "wave_width": 1250, "max_height": 480
    },
    {
        "name": "4. Капсулы с затуханием в точки",
        "wave_type": "linear", "num_bars": 49, "bar_thickness": 16,
        "roundness": 100, "wave_width": 1400, "max_height": 520
    },
    {
        "name": "5. Мега-маленькая (Компактная в обложку)",
        "wave_type": "linear", "num_bars": 9, "bar_thickness": 28,
        "roundness": 100, "wave_width": 360, "max_height": 300
    },
    {
        "name": "6. Двухсторонняя (Вокал сверху / Бас снизу)",
        "wave_type": "split", "num_bars": 85, "bar_thickness": 6,
        "roundness": 20, "wave_width": 1400, "max_height": 420,
        "color1": "#3D5A80", "color2": "#F5C518"
    },
    {
        "name": "7. Круговая волна (Активное кольцо 360°)",
        "wave_type": "circle", "num_bars": 84, "bar_thickness": 7,
        "roundness": 100, "wave_width": 560, "max_height": 250
    },
]

DUAL_PALETTES = [
    ("Чистый Белый", "#FFFFFF", "#FFFFFF"),
    ("Вокал и Бас", "#3D5A80", "#F5C518"),
    ("Неоновый Киберпанк", "#00F5D4", "#9B5DE5"),
    ("Тёплый Закат", "#FF4D6D", "#FFB703"),
    ("Ледяной Фиолет", "#FFFFFF", "#A29BFE"),
    ("Океан и Мята", "#00BBF9", "#00F5D4"),
    ("Spotify Неон", "#1DB954", "#A8FF78"),
    ("Огненный Бит", "#FF2A54", "#FF9E00"),
    ("Лавандовый Сон", "#E0AAFF", "#7209B7"),
    ("Серебро и Графит", "#E2E2EC", "#5C677D"),
]

SINGLE_SWATCHES = [
    "#FFFFFF", "#E2E2EC", "#8D99AE", "#3D5A80", "#2B2D42",
    "#FF4D6D", "#FF2A54", "#FF758F", "#FF9E00", "#F5C518",
    "#00F5D4", "#1DB954", "#52B788", "#00BBF9", "#3A86FF",
    "#A29BFE", "#9B5DE5", "#7209B7", "#F15BB5", "#FEE440",
]

APP_STYLESHEET = """
#MainContainer, #PaletteContainer {
    background-color: #121217;
    border: 1px solid #2A2A38;
    border-radius: 20px;
}
#CardFrame {
    background-color: #1A1A22;
    border: 1px solid #252530;
    border-radius: 14px;
}
QLabel {
    color: #E2E2EC;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
#TitleLabel {
    color: #FFFFFF;
    font-size: 15px;
    font-weight: bold;
}
#MutedLabel {
    color: #9A9AA8;
    font-size: 13px;
}
#HintLabel {
    color: #8A8AA0;
    font-size: 11px;
}
#TimeLabel {
    color: #8A75FF;
    font-weight: bold;
    font-size: 14px;
}
QPushButton {
    background-color: #262632;
    color: #FFFFFF;
    border: 1px solid #343444;
    border-radius: 10px;
    padding: 7px 14px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #323242;
    border-color: #4A4A60;
}
QPushButton:disabled {
    background-color: #1C1C24;
    color: #555562;
    border-color: #24242E;
}
#AccentBtn {
    background-color: #6C5CE7;
    border: none;
}
#AccentBtn:hover {
    background-color: #7E6FF0;
}
#ExportBtn {
    background-color: #00B894;
    color: #FFFFFF;
    border: none;
    padding: 9px 18px;
}
#ExportBtn:hover {
    background-color: #10C8A4;
}
#ExportBtn:disabled {
    background-color: #1E2E2B;
    color: #556B66;
}
#WinBtn, #CloseBtn {
    background-color: #20202A;
    border-radius: 8px;
    padding: 0px;
}
#WinBtn:hover {
    background-color: #323242;
}
#CloseBtn:hover {
    background-color: #E84118;
}
QComboBox {
    background-color: #242430;
    color: #FFFFFF;
    border: 1px solid #343446;
    border-radius: 9px;
    padding: 6px 12px;
    font-size: 13px;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #1E1E28;
    color: #FFFFFF;
    selection-background-color: #6C5CE7;
    border-radius: 8px;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #282836;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #6C5CE7;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 2px solid #6C5CE7;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 8px;
}
QProgressBar {
    background-color: #242430;
    border-radius: 8px;
    text-align: center;
    color: white;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #00B894;
    border-radius: 8px;
}
QLineEdit {
    background-color: #22222E;
    color: #FFFFFF;
    border: 1px solid #3A3A4E;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 13px;
}
QToolTip {
    background-color: #1E1E2A;
    color: #FFFFFF;
    border: 1px solid #6C5CE7;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 12px;
}
"""