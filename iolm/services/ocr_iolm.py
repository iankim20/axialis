from __future__ import annotations

import os
import base64
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import cv2
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw

# 1) .env 로부터 환경변수 로딩
#    - 보통 'python manage.py runserver' / 'celery -A Axialis worker' 를
#      프로젝트 루트에서 실행하면, 그냥 load_dotenv() 만 해도 루트의 .env 를 찾는다.
load_dotenv()

# 2) 환경변수에서 OPENAI_API_KEY 읽기
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in environment")

# 3) OpenAI 클라이언트 생성
client = OpenAI(api_key=API_KEY)

PTNT_INFO_INSTRUCTIONS = """
You are an OCR agent for the patient header of an ophthalmology IOL biometry report.
Input: a cropped header image containing patient and clinic info from an IOLMaster-style page.
Task: read the text and return this JSON ONLY:

{
  "ptnt_name": "",
  "ptnt_dob": "",
  "ptnt_sex": "",
  "ptnt_id": "",
  "exam_date": ""
}

Rules:
- ptnt_name: text near “환자” or “Patient”.
- ptnt_dob: text near “생년월일” or “Date of Birth”. Keep the visible format.
- ptnt_sex: map “남”→"M", “여”→"F". If unclear, return "".
- ptnt_id: text near “환자 ID” or “Patient ID”.

- exam_date:
  - The clinical exam / measurement date for this IOL biometry.
  - Look for text near labels such as “측정날짜”, “측정일자”, “Date of measurement”, “Exam date”, or similar.
  - The header may also contain "보정 검사 날짜" or "Date of calibration" close to the exam date.
    When multiple candidate dates appear, choose the **chronologically latest** date as exam_date.
  - Keep the visible format.
  - Do NOT use the patient date of birth as exam_date.

If any field is unreadable or absent, set it to "".
Return ONLY the JSON object with these exact keys.
""".strip()

BIOMETRY_INSTRUCTIONS = """
You are a vision OCR agent for ophthalmology IOLMaster biometry reports.
Input: a cropped biometry panel for ONE eye only (either OD or OS).
Output: return ONLY one JSON object with this structure:

{
  "measurements": [
    {
      "eye": "OD",
      "LS": "", "VS": "", "LVC": "",
      "AL": 0.0, "ACD": 0.0, "LT": 0.0, "CCT": 0, "WTW": 0.0,
      "K1": 0.0, "K1_m": 0, "K2": 0.0, "K2_m": 0,
      "TK1": 0.0, "TK1_m": 0, "TK2": 0.0, "TK2_m": 0,
      "missing_count": 0
    }
  ],
  "wrong": 0
}

Rules:

- The single object in "measurements"[0] corresponds to the visible eye only.
- "eye": set to "OD" or "OS" depending on the label in the crop.  
  If you cannot determine the side, set "eye": "".

Normalization:
- Remove units and symbols.
- Diopters (K/TK): decimal (e.g., 42.63).
- Angles: integers 0–179.
- AL/ACD/LT/WTW: mm as decimal.
- CCT: integer micrometers.
- If the CCT row or value is NOT visible in this crop, set CCT to 0.
  Never guess or infer a typical value. Only use numbers that are exactly
  visible in the image.
- If any value is unreadable, set it to 0 (numbers) or "" (strings).

Soft sanity ranges (re-check if far outside):  
AL 15–35 mm, ACD 1.0–5.5 mm, LT 1–8 mm, CCT 200–700 μm, WTW 8–16 mm, K/TK 30–70 D.

Extraction rules:
1) Use the main biometry summary tile for AL, ACD, LT, CCT, WTW, K and TK. Ignore IOL suggestion tiles.
2) K1_m, K2_m, TK1_m, TK2_m are the meridian angles aligned horizontally with their K/TK values.
   - Ensure K1_m and K2_m differ by 90°, and TK1_m and TK2_m differ by 90°. If not, re-check and correct.
   - TK1_m must come from the TK row, not from the K row. If TK1_m == K2_m, re-read TK1_m from the correct position.
3) LS, VS, LVC are taken from the eye’s status box:
   - LS (Lens Status): use the on-page wording; typically (or Korean equivalents):
     Aphakic, Phakic, Phakic IOL, Piggyback IOL, Pseudophakia, Piggyback Silicone IOL,
     Pseudophakic Silicone, Pseudophakic PMMA.
   - VS (Vitreous Status): use the on-page wording; typically (or Korean equivalents):
     Post-Vitrectomy, Silicone Oil, or Vitreous Only.
   - LVC (Laser Vision Correction): use the on-page wording; typically (or Korean equivalents):
     RK, PRK, LASIK, LASEK, or “none/치료받지 않음/—”.
4) Before returning:
   - If K1 > K2, swap K1/K2 and their meridians K1_m/K2_m.
   - If TK1 > TK2, swap TK1/TK2 and TK1_m/TK2_m.
   - missing_count = number of zeros among {AL, ACD, LT, CCT, WTW, K1, K2, TK1, TK2}.
4-bis) If any of {AL, ACD, LT, CCT, WTW, K1, K2, TK1, TK2} is not explicitly
   visible as a number in the crop, you MUST set that field to 0 instead of
   guessing a plausible value.

5) If the crop is clearly not an IOLMaster-style biometry panel or the eye is unreadable, set "wrong": 1 and keep default values.

Return ONLY the JSON object, with no extra keys or text.

""".strip()

PTNT_INFO_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "ptnt_name":   {"type": "string"},
        "ptnt_dob":    {"type": "string"},
        "ptnt_sex":    {"type": "string"},
        "ptnt_id":     {"type": "string"},
        "exam_date":   {"type": "string"},
    },
    "required": ["ptnt_name", "ptnt_dob", "ptnt_sex", "ptnt_id", "exam_date"],
    "additionalProperties": False,
}

BIOMETRY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "measurements": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "eye":   {"type": "string"},
                    "LS":    {"type": "string"},
                    "VS":    {"type": "string"},
                    "LVC":   {"type": "string"},
                    "AL":    {"type": "number"},
                    "ACD":   {"type": "number"},
                    "LT":    {"type": "number"},
                    "CCT":   {"type": "integer"},
                    "WTW":   {"type": "number"},
                    "K1":    {"type": "number"},
                    "K1_m":  {"type": "integer", "minimum": 0, "maximum": 179},
                    "K2":    {"type": "number"},
                    "K2_m":  {"type": "integer", "minimum": 0, "maximum": 179},
                    "TK1":   {"type": "number"},
                    "TK1_m": {"type": "integer", "minimum": 0, "maximum": 179},
                    "TK2":   {"type": "number"},
                    "TK2_m": {"type": "integer", "minimum": 0, "maximum": 179},
                    "missing_count": {"type": "integer", "minimum": 0},
                },
                "required": [
                    "eye", "LS", "VS", "LVC",
                    "AL", "ACD", "LT", "CCT", "WTW",
                    "K1", "K1_m", "K2", "K2_m",
                    "TK1", "TK1_m", "TK2", "TK2_m",
                    "missing_count",
                ],
                "additionalProperties": False,
            },
        },
        "wrong": {
            "type": "integer",
            "enum": [0, 1],
        },
    },
    "required": ["measurements", "wrong"],
    "additionalProperties": False,
}

def image_array_to_data_url(img: np.ndarray, fmt: str = "png") -> str:
    ext = ".png" if fmt.lower() == "png" else ".jpg"
    mime = "image/png" if ext == ".png" else "image/jpeg"

    success, buf = cv2.imencode(ext, img)
    if not success:
        raise RuntimeError("Failed to encode image for data URL")

    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"



def resize_for_detail_high(img: np.ndarray) -> np.ndarray:
    """
    OpenAI detail:"high" 규칙과 동일한 방식으로 리사이즈:
      1) 2048x2048 정사각형 안에 들어가도록 (다운스케일만)
      2) 짧은 변이 768px 이하가 되도록 (역시 다운스케일만)
    """
    h, w = img.shape[:2]
    longest = max(w, h)
    shortest = min(w, h)

    # 1단계 + 2단계를 한 번에: 항상 다운스케일만
    scale = min(
        2048.0 / float(longest),
        768.0 / float(shortest),
    )

    if scale == 1.0:
        # 규칙 상 더 줄일 필요가 없는 경우 (이미 충분히 작음)
        return img

    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    # 다운스케일이므로 INTER_AREA가 보통 OCR에 가장 유리
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    print(scale)
    return resized

def detect_split_x(img: np.ndarray) -> int:
    h, w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )

    kernel_h = max(40, h // 15)
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, kernel_h)
    )
    vertical = cv2.erode(th, vertical_kernel, iterations=1)
    vertical = cv2.dilate(vertical, vertical_kernel, iterations=1)

    col_sum = vertical.sum(axis=0)

    left = int(w * 0.2)
    right = int(w * 0.8)
    central = col_sum[left:right]
    max_idx = int(np.argmax(central))
    x_split = left + max_idx

    x_split = max(0, min(w - 1, x_split))
    return x_split

def detect_horizontal_split_y(img: np.ndarray) -> int:
    """
    patient info 블록과 biometry panel을 나누는
    '가장 위쪽의 진한 가로선'의 y 좌표를 리턴.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    kernel_w = max(w // 4, 100)   # 페이지 가로의 1/4 이상, 최소 100픽셀
    horiz_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (kernel_w, 1),
    )

    horiz = cv2.erode(th, horiz_kernel, iterations=1)
    horiz = cv2.dilate(horiz, horiz_kernel, iterations=1)

    row_sum = horiz.sum(axis=1)   # shape: (h,)

    search_top = int(h * 0.10)     # 필요하면 0.15 정도로 조절
    search_bottom = int(h * 0.5)  # 너무 아래쪽(Zeiss 로고 근처)도 제외
    candidate_rows = np.arange(search_top, search_bottom)
    candidate_vals = row_sum[search_top:search_bottom]

    threshold = candidate_vals.max() * 0.4   # 0.3은 경험적 비율, 조절 가능
    strong_rows = candidate_rows[candidate_vals > threshold]

    if len(strong_rows) == 0:
        y_split = int(search_top + np.argmax(candidate_vals))
    else:
        # 7) 그 중에서 "가장 위쪽" 행이 우리가 원하는 patient/biometry 경계선
        y_split = int(strong_rows.min())

    # 이미지 범위 클리핑
    y_split = max(0, min(h - 1, y_split))
    return y_split

def split_into_segments(img: np.ndarray, x_split: int, y_split: int) -> Dict[str, np.ndarray]:
    h, w = img.shape[:2]

    y_split = max(0, min(h, y_split))
    x_split = max(0, min(w, x_split))

    ptnt_info = img[0:y_split, :, :].copy()
    od_data   = img[y_split:h, 0:x_split, :].copy()
    os_data   = img[y_split:h, x_split:w, :].copy()

    return {
        "ptnt_info": ptnt_info,
        "od_data": od_data,
        "os_data": os_data,
    }

def parse_json_from_response(resp) -> Dict[str, Any]:
    """
    Responses API에서 JSON Schema text를 꺼내는 헬퍼.
    - resp.output 리스트에서 type == "message" 인 항목을 찾고,
    - 그 message.content 중 type == "output_text" 를 골라 JSON 로드.
    """
    for item in resp.output:
        # 보통 ResponseOutputMessage
        if getattr(item, "type", None) == "message":
            if not getattr(item, "content", None):
                continue

            for block in item.content:
                # 보통 ResponseOutputText
                if getattr(block, "type", None) == "output_text":
                    text = block.text
                    return json.loads(text)

    raise RuntimeError(f"Could not find output_text message in response: {resp}")

def ocr_ptnt_info(
    img_header: np.ndarray,
    model_ptnt: str = "gpt-4.1",
    effort_ptnt: str = "medium",  # "low" | "medium" | "high"
    temp_ptnt: float = 0.0,
    max_tokens_ptnt: int | None = None,
    top_p_ptnt: float = 0.15,
)  -> Dict[str, Any]:
    data_url = image_array_to_data_url(img_header)

    user_text = (
        "This image is the patient header (top area) of an IOLMaster-style "
        "ophthalmology biometry report. Extract patient info according to the JSON schema."
    )

    # 공통 extra_args: 모델 타입에 따라 reasoning 또는 temp/top_p/tokens 넣기
    extra_args: Dict[str, Any] = {}

    if is_reasoning_model(model_ptnt):
        extra_args["reasoning"] = {"effort": effort_ptnt}
    else:
        extra_args["temperature"] = float(temp_ptnt)
        extra_args["top_p"] = float(top_p_ptnt)
        if max_tokens_ptnt is not None:
            extra_args["max_output_tokens"] = int(max_tokens_ptnt)
    
    resp = client.responses.create(
        model=model_ptnt,
        input=[
            {
                "role": "developer",
                "content": [
                    {"type": "input_text", "text": PTNT_INFO_INSTRUCTIONS},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": data_url, "detail": "high"},
                ],
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "ptnt_info_schema",
                "strict": True,
                "schema": PTNT_INFO_SCHEMA,
            }
        },
        store=False,
        **extra_args,
    )
    # print(resp)

    usage_stats = extract_usage_stats(resp)
    data = parse_json_from_response(resp)
    return data, usage_stats

def ocr_biometry_single_eye(
    img_eye: np.ndarray,
    eye_hint: str,
    model_biometry: str = "gpt-4.1",
    effort_biometry: str = "medium",  # "low" | "medium" | "high"
    temp_biometry: float = 0.0,
    max_tokens_biometry: int | None = None,
    top_p_biometry: float = 0.15,
) -> Dict[str, Any]:
    data_url = image_array_to_data_url(img_eye)

    user_text = (
        f"This image is the biometry panel for ONE eye ({eye_hint}) from an "
        "IOLMaster-style ophthalmology exam. Extract measurements according to the JSON schema."
    )

    # 공통 extra_args: 모델 타입에 따라 reasoning 또는 temp/top_p/tokens 넣기
    extra_args: Dict[str, Any] = {}

    if is_reasoning_model(model_biometry):
        extra_args["reasoning"] = {"effort": effort_biometry}
    else:
        extra_args["temperature"] = float(temp_biometry)
        extra_args["top_p"] = float(top_p_biometry)
        if max_tokens_biometry is not None:
            extra_args["max_output_tokens"] = int(max_tokens_biometry)

    resp = client.responses.create(
        model=model_biometry,
        input=[
            {
                "role": "developer",
                "content": [
                    {"type": "input_text", "text": BIOMETRY_INSTRUCTIONS},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": data_url, "detail": "high"},
                ],
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "biometry_single_eye_schema",
                "strict": True,
                "schema": BIOMETRY_SCHEMA,
            }
        },
        store=False,
        **extra_args,
    )

    usage_stats = extract_usage_stats(resp)
    data = parse_json_from_response(resp)
    return data, usage_stats

def process_iolm_image(
    image_path: Path,
    model_ptnt: str = "gpt-4.1",
    effort_ptnt: str = "medium",
    temp_ptnt: float = 0.0,
    top_p_ptnt: float = 0.15,
    max_tokens_ptnt: Optional[int] = 400,
    
    model_biometry: str = "gpt-4.1",
    effort_biometry: str = "medium",
    temp_biometry: float = 0.0,
    top_p_biometry: float = 0.15,
    max_tokens_biometry: Optional[int] = 400,
    
    scale_factor: float = 1.5,  
) -> Dict[str, Any]:
    img = cv2.imread(str(image_path))
    if img is None:
        raise RuntimeError(f"Cannot read image: {image_path}")

    t0 = time.perf_counter()

    # 1) CV split (x/y)
    x_split = detect_split_x(img)
    y_split = detect_horizontal_split_y(img)
    segments = split_into_segments(img, x_split, y_split)
    ptnt_info_img = segments["ptnt_info"]
    od_img = segments["od_data"]
    os_img = segments["os_data"]

    t1 = time.perf_counter()
    
    ptnt_info_resized = resize_for_detail_high(ptnt_info_img)
    od_resized = resize_for_detail_high(od_img)
    os_resized = resize_for_detail_high(os_img)

    # 2) ptnt header OCR
    ptnt_info, usage_ptnt = ocr_ptnt_info(
        ptnt_info_resized,
        model_ptnt=model_ptnt,
        effort_ptnt=effort_ptnt,
        temp_ptnt=temp_ptnt,
        max_tokens_ptnt=max_tokens_ptnt,
        top_p_ptnt=top_p_ptnt,
    )

    t2 = time.perf_counter()

    # 3) OD biometry OCR
    od_biometry, usage_od = ocr_biometry_single_eye(
        od_resized,
        eye_hint="OD",
        model_biometry=model_biometry,
        effort_biometry=effort_biometry,
        temp_biometry=temp_biometry,
        max_tokens_biometry=max_tokens_biometry,
        top_p_biometry=top_p_biometry,
    )

    t3 = time.perf_counter()

    # 4) OS biometry OCR
    os_biometry, usage_os = ocr_biometry_single_eye(
        os_resized,
        eye_hint="OS",
        model_biometry=model_biometry,
        effort_biometry=effort_biometry,
        temp_biometry=temp_biometry,
        max_tokens_biometry=max_tokens_biometry,
        top_p_biometry=top_p_biometry,
    )

    t4 = time.perf_counter()

    timing = {
        "total_sec": t4 - t0,
        "cv_split_sec": t1 - t0,
        "ptnt_ocr_sec": t2 - t1,
        "od_ocr_sec": t3 - t2,
        "os_ocr_sec": t4 - t3,
    }

    usage = {
        "ptnt": usage_ptnt,
        "od": usage_od,
        "os": usage_os,
    }

    return {
        "image": str(image_path),
        "splits": {"x_split": x_split, "y_split": y_split},
        "ptnt_info": ptnt_info,
        "od": od_biometry,
        "os": os_biometry,
        "timing": timing,
        "usage": usage,
    }
def normalize_model_family(full_name: str) -> str:
    """
    Map versioned model name (e.g. 'gpt-4.1-2025-04-14') to
    a pricing key like 'gpt-4.1' or 'o4-mini'.
    """
    name = full_name.lower()
    prefixes = [
        "gpt-4.1-nano",
        "gpt-4.1-mini",
        "gpt-4.1",
        "gpt-4o",
        "o4-mini",
        "o3",
        "o1",
    ]
    for p in prefixes:
        if name.startswith(p):
            return p
    return full_name  # unknown family; pricing dict may not have it

# ---------- pricing (USD per 1M tokens, STANDARD tier) ----------
MODEL_PRICING = {
    "gpt-5.1":       {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5":         {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-4.1":       {"input": 2.00, "cached_input": 0.50,  "output": 8.00},
    "gpt-4.1-mini":  {"input": 0.40, "cached_input": 0.10,  "output": 1.60},
    "gpt-4.1-nano":  {"input": 0.10, "cached_input": 0.025, "output": 0.40},
    "gpt-4o":        {"input": 2.50, "cached_input": 1.25,  "output": 10.00},
    "o4-mini":       {"input": 1.10, "cached_input": 0.275, "output": 4.40},
    "o3":            {"input": 2.00, "cached_input": 0.50,  "output": 8.00},
    "o3-pro":        {"input": 20.0, "cached_input": None,  "output": 80.00},
    "o3-deep-research": {"input": 10.0, "cached_input": 2.50, "output": 40.00},
    "o1":            {"input": 15.0, "cached_input": 7.50,  "output": 60.00},
}

def compute_text_cost_usd(
    model_name: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
) -> Dict[str, Optional[float]]:
    fam = normalize_model_family(model_name)
    pricing = MODEL_PRICING.get(fam)
    if pricing is None:
        return {
            "family": fam,
            "input_cost_usd": None,
            "cached_input_cost_usd": None,
            "output_cost_usd": None,
            "total_cost_usd": None,
        }

    fresh_tokens = max(0, input_tokens - cached_tokens)

    in_rate = pricing["input"]
    cached_rate = pricing.get("cached_input")
    out_rate = pricing["output"]

    # If cached rate is not defined (e.g. caching not supported for that model),
    # bill cached tokens at normal input price.
    if cached_rate is None:
        cached_rate = in_rate

    input_cost = fresh_tokens * in_rate / 1_000_000.0
    cached_cost = cached_tokens * cached_rate / 1_000_000.0
    output_cost = output_tokens * out_rate / 1_000_000.0

    return {
        "family": fam,
        "input_cost_usd": input_cost,
        "cached_input_cost_usd": cached_cost,
        "output_cost_usd": output_cost,
        "total_cost_usd": input_cost + cached_cost + output_cost,
    }

def extract_usage_stats(resp) -> Dict[str, Any]:
    """
    Flatten Response.usage into a dict, including cached tokens
    and cost breakdown.
    """
    u = resp.usage

    input_tokens = int(u.input_tokens)
    output_tokens = int(u.output_tokens)
    total_tokens = int(u.total_tokens)

    cached_tokens = 0
    if getattr(u, "input_tokens_details", None) is not None:
        cached_tokens = int(getattr(u.input_tokens_details, "cached_tokens", 0))

    reasoning_tokens = 0
    if getattr(u, "output_tokens_details", None) is not None:
        reasoning_tokens = int(getattr(u.output_tokens_details, "reasoning_tokens", 0))

    cost = compute_text_cost_usd(
        resp.model,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
    )

    return {
        "model": resp.model,
        "family": cost["family"],
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "fresh_input_tokens": max(0, input_tokens - cached_tokens),
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "input_cost_usd": cost["input_cost_usd"],
        "cached_input_cost_usd": cost["cached_input_cost_usd"],
        "output_cost_usd": cost["output_cost_usd"],
        "total_cost_usd": cost["total_cost_usd"],
    }

def is_reasoning_model(model_name: str) -> bool:
    n = model_name.lower()
    return n.startswith("o1") or n.startswith("o3") or n.startswith("o4")
