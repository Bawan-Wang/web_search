from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import ssl
import tempfile
from urllib.request import urlopen


THSR_SCHEDULE_URL = "https://www.thsrc.com.tw/ArticleContent/a3b630bb-1066-4352-a1ef-58c7b4e8ef7c"
THSR_TIMETABLE_PDF_URL = "https://www.thsrc.com.tw/Attachment/Download?pageID=a3b630bb-1066-4352-a1ef-58c7b4e8ef7c&id=b5e78f70-fa6d-4f75-8f31-a13387d7ea88"
THSR_KEYWORDS = ("高鐵", "班次", "車次", "時刻表", "票價")
THSR_STATIONS = ["南港", "台北", "板橋", "桃園", "新竹", "苗栗", "台中", "彰化", "雲林", "嘉義", "台南", "左營"]
ROUTE_QUERY_PREFIXES = ("幫我查現在", "幫我查", "請幫我", "麻煩幫我", "請問", "搜尋", "查詢", "查一下", "現在", "今天", "查")
ROUTE_QUERY_FILLERS = ("高鐵", "最近班次", "班次", "車次", "時刻表", "票價", "如何", "怎麼搭", "怎麼去")
TIMETABLE_ROW_CACHE: dict[str, list[dict[str, str]]] = {}


@dataclass(frozen=True)
class ColumnSection:
    train_x: float
    station_xs: tuple[float, ...]
    x_min: float
    x_max: float


THSR_COLUMN_SECTIONS = (
    ColumnSection(
        train_x=32.0,
        station_xs=(109.9, 147.2, 184.4, 221.7, 259.0, 296.2, 333.5, 370.8, 408.1, 445.3, 482.6, 519.9),
        x_min=0,
        x_max=560,
    ),
    ColumnSection(
        train_x=596.7,
        station_xs=(676.4, 713.6, 750.9, 788.2, 825.5, 862.7, 900.0, 937.3, 974.5, 1011.8, 1049.1, 1086.3),
        x_min=560,
        x_max=1120,
    ),
)


def is_thsr_query(query: str) -> bool:
    return "高鐵" in query


def needs_transport_search(query: str) -> bool:
    return any(keyword in query for keyword in THSR_KEYWORDS)


def extract_route_stations(query: str) -> tuple[str, str]:
    cleaned_query = _normalize_route_query(query)
    match = re.search(r"([\u4e00-\u9fff]{1,6})(?:站)?到([\u4e00-\u9fff]{1,6})(?:站)?", cleaned_query)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def build_thsr_reply(user_voice_input: str, context: str = "") -> str:
    if not is_thsr_query(user_voice_input):
        return ""

    origin, destination = extract_route_stations(user_voice_input)
    route_text = _build_route_text(origin, destination)

    if origin and destination:
        next_trains = _find_next_thsr_trains(origin, destination)
        if next_trains:
            segments = [
                f"{train['train_no']}車次 {train['departure']}發 {train['arrival']}到"
                for train in next_trains
            ]
            return f"{route_text}最近班次：" + "；".join(segments) + "。"

    if "時刻表與票價查詢" in context or "台灣高鐵" in context:
        return f"我目前只查到台灣高鐵官方查詢入口，{route_text}的最近班次請到 {THSR_SCHEDULE_URL} 查詢。"

    return f"我目前沒有查到足夠的高鐵班次細節，{route_text}請直接到 {THSR_SCHEDULE_URL} 查詢。"


def _normalize_route_query(query: str) -> str:
    cleaned_query = re.sub(r"[？?，,。.!！\s]", "", query)
    stripped_prefix = True
    while stripped_prefix:
        stripped_prefix = False
        for prefix in ROUTE_QUERY_PREFIXES:
            if cleaned_query.startswith(prefix):
                cleaned_query = cleaned_query[len(prefix):]
                stripped_prefix = True
                break
    for keyword in ROUTE_QUERY_FILLERS:
        cleaned_query = cleaned_query.replace(keyword, "")
    return cleaned_query.replace("的", "")


def _build_route_text(origin: str, destination: str) -> str:
    if origin and destination:
        return f"{origin}到{destination}"
    return "你的路線"


def _download_thsr_timetable_pdf() -> Path:
    pdf_path = Path(tempfile.gettempdir()) / "thsr_timetable.pdf"
    if pdf_path.exists():
        return pdf_path

    ssl_context = ssl._create_unverified_context()
    with urlopen(THSR_TIMETABLE_PDF_URL, context=ssl_context, timeout=20) as response:
        pdf_path.write_bytes(response.read())
    return pdf_path


def _load_thsr_rows(direction: str) -> list[dict[str, str]]:
    if direction in TIMETABLE_ROW_CACHE:
        return TIMETABLE_ROW_CACHE[direction]

    try:
        from pypdf import PdfReader
    except Exception:
        return []

    pdf_path = _download_thsr_timetable_pdf()
    reader = PdfReader(str(pdf_path))
    page = reader.pages[_page_index_for_direction(direction)]
    items = _extract_pdf_items(page)
    stations = _stations_for_direction(direction)

    rows: list[dict[str, str]] = []
    for section in THSR_COLUMN_SECTIONS:
        rows.extend(_parse_rows_from_section(items, section, stations))

    TIMETABLE_ROW_CACHE[direction] = rows
    return rows


def _page_index_for_direction(direction: str) -> int:
    return 1 if direction == "southbound" else 0


def _stations_for_direction(direction: str) -> list[str]:
    if direction == "southbound":
        return THSR_STATIONS
    return list(reversed(THSR_STATIONS))


def _extract_pdf_items(page) -> list[tuple[float, float, str]]:
    items: list[tuple[float, float, str]] = []

    def visitor(text, cm, tm, font_dict, font_size):
        text = text.strip()
        if text:
            items.append((tm[4], tm[5], text))

    page.extract_text(visitor_text=visitor)
    return items


def _parse_rows_from_section(
    items: list[tuple[float, float, str]],
    section: ColumnSection,
    stations: list[str],
) -> list[dict[str, str]]:
    section_items = [
        (x, y, text)
        for x, y, text in items
        if section.x_min <= x <= section.x_max and 40 < y < 540
    ]
    grouped_rows: dict[float, list[tuple[float, str]]] = {}
    for x, y, text in section_items:
        grouped_rows.setdefault(round(y, 1), []).append((x, text))

    parsed_rows: list[dict[str, str]] = []
    for row_items in grouped_rows.values():
        row = _parse_single_row(row_items, section, stations)
        if row:
            parsed_rows.append(row)
    return parsed_rows


def _parse_single_row(
    row_items: list[tuple[float, str]],
    section: ColumnSection,
    stations: list[str],
) -> dict[str, str]:
    train_no = ""
    station_times = [""] * len(section.station_xs)

    for x, text in row_items:
        if abs(x - section.train_x) < 12 and re.fullmatch(r"\d{3,4}", text):
            train_no = text
        for index, station_x in enumerate(section.station_xs):
            if abs(x - station_x) < 12 and re.fullmatch(r"\d{2}:\d{2}", text):
                station_times[index] = text

    if not train_no:
        return {}

    row = {"train_no": train_no}
    for station, time_text in zip(stations, station_times):
        if time_text:
            row[station] = time_text
    return row


def _time_to_minutes(time_text: str) -> int:
    hour, minute = map(int, time_text.split(":"))
    return hour * 60 + minute


def _find_next_thsr_trains(origin: str, destination: str, limit: int = 3) -> list[dict[str, str]]:
    if origin not in THSR_STATIONS or destination not in THSR_STATIONS:
        return []

    direction = _direction_for_route(origin, destination)
    rows = _load_thsr_rows(direction)
    current_minutes = datetime.now().hour * 60 + datetime.now().minute

    candidates = []
    for row in rows:
        departure = row.get(origin)
        arrival = row.get(destination)
        if not departure or not arrival:
            continue
        if _time_to_minutes(departure) < current_minutes:
            continue
        candidates.append(
            {
                "train_no": row["train_no"],
                "departure": departure,
                "arrival": arrival,
            }
        )

    candidates.sort(key=lambda item: _time_to_minutes(item["departure"]))
    return candidates[:limit]


def _direction_for_route(origin: str, destination: str) -> str:
    if THSR_STATIONS.index(origin) < THSR_STATIONS.index(destination):
        return "southbound"
    return "northbound"