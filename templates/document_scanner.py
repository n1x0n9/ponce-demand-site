import os
import re
from pypdf import PdfReader
from docx import Document as DocxDocument

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None


# -----------------------------
# File extraction
# -----------------------------
def extract_text_from_pdf(path):
    text_parts = []
    reader = PdfReader(path)
    for page in reader.pages:
        try:
            text_parts.append(page.extract_text() or "")
        except Exception:
            pass
    return "\n".join(text_parts)


def extract_text_from_docx(path):
    doc = DocxDocument(path)
    return "\n".join([p.text for p in doc.paragraphs])


def extract_text_from_image(path):
    if Image is None or pytesseract is None:
        return ""

    try:
        img = Image.open(path)
        return pytesseract.image_to_string(img) or ""
    except Exception:
        return ""


def extract_text_from_file(path):
    lower = path.lower()
    if lower.endswith(".pdf"):
        return extract_text_from_pdf(path)
    if lower.endswith(".docx"):
        return extract_text_from_docx(path)
    if lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return extract_text_from_image(path)
    return ""


# -----------------------------
# General helpers
# -----------------------------
def clean_text(text):
    text = (text or "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_first(pattern, text, flags=re.IGNORECASE | re.DOTALL):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def normalize_name(name):
    if not name:
        return ""
    name = re.sub(r"\s+", " ", name).strip(" :,-")
    return name.title()


def sentence_case_fix(text):
    text = clean_text(text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        return ""
    return text + "."


def dedupe_keep_order(items):
    seen = set()
    result = []
    for item in items:
        key = clean_text(item).lower()
        if key and key not in seen:
            seen.add(key)
            result.append(clean_text(item))
    return result


def split_blocks(text):
    raw_blocks = re.split(r"\n\s*\n", clean_text(text))
    return [clean_text(block) for block in raw_blocks if clean_text(block)]


def clean_record_junk(text):
    text = clean_text(text)

    junk_patterns = [
        r"thank you for your referral\.?",
        r"this document has been.*?$",
        r"electronically signed.*?$",
        r"digitally signed.*?$",
        r"page \d+ of \d+",
        r"printed on .*?$",
        r"generated on .*?$",
        r"fax[: ].*?$",
        r"phone[: ].*?$",
    ]

    for pattern in junk_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)

    text = re.sub(r"\s+", " ", text).strip(" .,-")
    return text


# -----------------------------
# Core field extraction
# -----------------------------
def find_client_name(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    patterns = [
        r"\bPATIENT NAME[:\s]+([A-Z][A-Z ,.'\-]+)",
        r"\bNAME[:\s]+([A-Z][A-Z ,.'\-]+)",
        r"\bCLIENT NAME[:\s]+([A-Z][A-Z ,.'\-]+)",
    ]

    for pattern in patterns:
        value = extract_first(pattern, text, flags=re.IGNORECASE)
        if value:
            value = re.sub(r"\s+", " ", value).strip(" ,:-")
            if len(value.split()) >= 2:
                return normalize_name(value)

    for i, line in enumerate(lines):
        upper = line.upper()
        if upper.startswith("NAME:") or upper.startswith("PATIENT NAME:") or upper.startswith("CLIENT NAME:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return normalize_name(value)
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line.split()) >= 2:
                    return normalize_name(next_line)

    return ""


def find_claim_number(text):
    patterns = [
        r"CLAIM(?: NUMBER| NO\.?| #)?[:\s]+([A-Z0-9\-]+)",
        r"\bCLM[-\s]*([A-Z0-9\-]+)",
        r"\bFILE(?: NUMBER| NO\.?)[:\s]+([A-Z0-9\-]+)"
    ]
    for p in patterns:
        value = extract_first(p, text)
        if value:
            return value
    return ""


def find_loss_date(text):
    patterns = [
        r"DATE OF LOSS[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        r"LOSS DATE[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        r"\bDOL[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        r"ACCIDENT DATE[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})"
    ]
    for p in patterns:
        value = extract_first(p, text)
        if value:
            return value
    return ""


def find_service_date(text):
    patterns = [
        r"\bDATE OF SERVICE\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"\bDOS\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"\bSERVICE DATE\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"\bDATE\s*:\s*(\d{1,2}/\d{1,2}/\d{2,4})"
    ]
    for p in patterns:
        value = extract_first(p, text)
        if value:
            return value
    return ""


def find_all_dates(text):
    dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text)
    seen = []
    for d in dates:
        if d not in seen:
            seen.append(d)
    return seen


# -----------------------------
# Classification
# -----------------------------
ACCIDENT_TERMS = [
    "motor vehicle collision", "motor vehicle accident", "rear-end", "rear ended",
    "rear-ended", "t-bone", "intersection", "impact", "crash", "collision",
    "struck", "hit by", "insured", "at-fault", "police report", "liability",
    "failed to yield", "red light", "stop sign", "lane change"
]

MEDICAL_TERMS = [
    "mri", "ct", "x-ray", "xray", "findings", "impression", "history",
    "diagnosis", "diagnoses", "treatment", "therapy", "chiropractic",
    "physical therapy", "rehab", "orthopedic", "pain management", "provider",
    "clinic", "hospital", "radiology", "examination", "complains of", "complaint",
    "follow-up", "range of motion", "sprain", "strain", "effusion", "ligament"
]


def extract_accident_blocks(text):
    blocks = split_blocks(text)
    chosen = []

    for block in blocks:
        lower = block.lower()
        accident_score = sum(1 for t in ACCIDENT_TERMS if t in lower)
        medical_score = sum(1 for t in MEDICAL_TERMS if t in lower)

        if accident_score >= 2 and medical_score <= 2:
            chosen.append(block)
            continue

        if ("collision" in lower or "crash" in lower or "accident" in lower) and not any(
            x in lower for x in ["mri", "impression", "findings", "radiology", "therapy", "clinic", "hospital"]
        ):
            chosen.append(block)

    return dedupe_keep_order(chosen)


# -----------------------------
# Provider extraction
# -----------------------------
PROVIDER_KEYWORDS = [
    "clinic", "medical", "hospital", "radiology", "imaging", "rehab", "therapy",
    "orthopedic", "ortho", "chiropractic", "emergency", "pain", "surgery",
    "center", "centre", "diagnostic", "mri"
]

BAD_PROVIDER_LINE_STARTS = [
    "name:", "patient name:", "dob:", "date:", "history:", "findings:", "impression:",
    "technique:", "comparison:", "provider:", "diagnosis:", "chief complaint:",
    "complaints:", "examination:", "plan:", "assessment:"
]


def clean_provider_name(name):
    name = clean_text(name or "")
    if not name:
        return ""

    name = re.sub(r"\b(page|pg)\s*\d+\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(phone|fax|tel|ph)\b.*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(dob|date of birth|mrn|claim number|claim no\.?)\b.*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}", "", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" ,:-")

    bad_exact = {
        "history", "findings", "impression", "technique", "comparison",
        "diagnosis", "diagnoses", "treatment", "medical records", "records",
        "patient name", "date", "provider", "facility"
    }
    if name.lower() in bad_exact:
        return ""

    if len(name) < 4:
        return ""

    return normalize_name(name)


def find_provider_candidates(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = []

    for line in lines[:80]:
        lower = line.lower()

        if any(lower.startswith(x) for x in BAD_PROVIDER_LINE_STARTS):
            continue

        if len(line) > 95:
            continue

        if re.search(r"\b\d{1,5}\s+[A-Za-z]", line):
            continue

        if any(k in lower for k in PROVIDER_KEYWORDS):
            cleaned = clean_provider_name(line)
            if cleaned:
                candidates.append(cleaned)

    return dedupe_keep_order(candidates)


def pick_best_provider_name(text):
    candidates = find_provider_candidates(text)
    if not candidates:
        return ""

    facility_like = []
    person_like = []

    for c in candidates:
        lower = c.lower()
        if any(k in lower for k in ["clinic", "medical", "hospital", "radiology", "imaging", "center", "centre", "diagnostic", "therapy", "rehab"]):
            facility_like.append(c)
        else:
            person_like.append(c)

    if facility_like:
        return facility_like[0]
    return candidates[0]


def find_provider_type(provider_name):
    upper = (provider_name or "").upper()
    if "MRI" in upper or "RADIOLOGY" in upper or "IMAGING" in upper or "DIAGNOSTIC" in upper:
        return "Radiology / Imaging"
    if "HOSPITAL" in upper or "EMERGENCY" in upper:
        return "Hospital / Emergency"
    if "THERAPY" in upper or "REHAB" in upper:
        return "Physical Therapy / Rehab"
    if "CHIROPRACTIC" in upper:
        return "Chiropractic"
    if "ORTHO" in upper or "ORTHOPEDIC" in upper or "SURGERY" in upper:
        return "Orthopedic"
    if "PAIN" in upper:
        return "Pain Management"
    if "CLINIC" in upper or "MEDICAL" in upper or "CENTER" in upper or "CENTRE" in upper:
        return "Medical Provider"
    return ""


# -----------------------------
# Medical detail extraction
# -----------------------------
def find_history(text):
    patterns = [
        r"HISTORY[:\s]*(.*?)(?:TECHNIQUE:|FINDINGS:|IMPRESSION:|EXAMINATION:|$)",
        r"CHIEF COMPLAINT[:\s]*(.*?)(?:HPI:|PHYSICAL EXAM|ASSESSMENT:|PLAN:|$)",
        r"COMPLAINTS?[:\s]*(.*?)(?:ASSESSMENT:|PLAN:|FINDINGS:|IMPRESSION:|$)"
    ]
    for pattern in patterns:
        value = extract_first(pattern, text)
        if value:
            return clean_record_junk(value)
    return ""


def find_findings(text):
    return clean_record_junk(extract_first(r"FINDINGS[:\s]*(.*?)(?:IMPRESSION:|CONCLUSION:|$)", text))


def find_impression(text):
    value = extract_first(r"IMPRESSION[:\s]*(.*?)(?:SIGNED|ELECTRONICALLY SIGNED|DIGITALLY SIGNED|$)", text)
    if value:
        return clean_record_junk(value)
    value = extract_first(r"CONCLUSION[:\s]*(.*?)(?:SIGNED|ELECTRONICALLY SIGNED|DIGITALLY SIGNED|$)", text)
    return clean_record_junk(value)


def find_exam_type(text):
    patterns = [
        r"(MRI OF [A-Z0-9 \-/]+)",
        r"(MRI [A-Z0-9 \-/]+ WITHOUT CONTRAST)",
        r"(MRI [A-Z0-9 \-/]+ WITH CONTRAST)",
        r"(CT OF [A-Z0-9 \-/]+)",
        r"(X-?RAY OF [A-Z0-9 \-/]+)",
        r"(XRAY OF [A-Z0-9 \-/]+)"
    ]
    for p in patterns:
        value = extract_first(p, text, flags=re.IGNORECASE)
        if value:
            value = clean_record_junk(value.upper())
            return value
    return ""


def find_objective_findings(text):
    keywords = [
        "disc bulge", "disc herniation", "annular tear", "radiculopathy",
        "nerve impingement", "joint effusion", "ligament", "tear", "edema",
        "stenosis", "fracture", "spasm", "effusion", "strain", "sprain"
    ]

    findings = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        low = line.lower()

        if any(k in low for k in keywords):
            if "no fracture" in low:
                continue
            if "unremarkable" in low and "effusion" not in low:
                continue
            cleaned = clean_record_junk(line)
            if cleaned:
                findings.append(cleaned)

    findings = dedupe_keep_order(findings)
    return findings[:4]


def extract_complaints(text):
    source = clean_text(" ".join([
        find_history(text),
        text[:2500]
    ])).lower()

    complaint_map = [
        ("neck pain", ["neck pain", "cervical pain"]),
        ("back pain", ["back pain", "low back pain", "lumbar pain", "thoracic pain"]),
        ("headaches", ["headache", "headaches"]),
        ("shoulder pain", ["shoulder pain"]),
        ("arm pain", ["arm pain"]),
        ("wrist pain", ["wrist pain"]),
        ("hand pain", ["hand pain"]),
        ("hip pain", ["hip pain"]),
        ("knee pain", ["knee pain"]),
        ("ankle pain", ["ankle pain"]),
        ("radiating pain", ["radiating pain", "radicular pain"]),
        ("numbness", ["numbness"]),
        ("tingling", ["tingling"]),
        ("weakness", ["weakness"])
    ]

    found = []
    for label, terms in complaint_map:
        if any(term in source for term in terms):
            found.append(label)

    return found


def summarize_impression(impression):
    impression = clean_record_junk(impression)
    if not impression:
        return ""

    impression = re.sub(r"\s+", " ", impression).strip(" .")
    impression = impression[:260].rsplit(" ", 1)[0] if len(impression) > 260 else impression
    return impression


def build_provider_list(provider_name, provider_type, dates):
    if not provider_name:
        return []

    if not dates:
        date_range = ""
    elif len(dates) == 1:
        date_range = dates[0]
    else:
        date_range = f"{dates[0]} to {dates[-1]}"

    return [{
        "provider_name": provider_name,
        "provider_type": provider_type,
        "date_range": date_range
    }]


def build_chronology(provider_name, text, dates):
    history = find_history(text)
    impression = summarize_impression(find_impression(text))
    exam = find_exam_type(text)

    return [{
        "date_of_service": dates[0] if dates else "",
        "provider": provider_name,
        "chief_complaints": history,
        "diagnoses": impression,
        "treatment_performed": exam,
        "imaging_reviewed": exam,
        "referrals": ""
    }]


def build_imaging_summary(text, provider_name, dates, impression):
    exam = find_exam_type(text)
    impression = summarize_impression(impression)

    if not exam and not impression:
        return []

    body_region = ""
    exam_upper = exam.upper()
    if "WRIST" in exam_upper:
        body_region = "Wrist"
    elif "SHOULDER" in exam_upper:
        body_region = "Shoulder"
    elif "CERVICAL" in exam_upper:
        body_region = "Cervical spine"
    elif "LUMBAR" in exam_upper:
        body_region = "Lumbar spine"
    elif "THORACIC" in exam_upper:
        body_region = "Thoracic spine"
    elif "KNEE" in exam_upper:
        body_region = "Knee"

    return [{
        "date": dates[0] if dates else "",
        "study": exam,
        "body_region": body_region,
        "provider": provider_name,
        "impression_verbatim": impression
    }]


def find_high_value_indicators(text):
    indicators = []
    lower = text.lower()

    rules = [
        ("disc herniation", "Disc herniation may support a higher-value claim because it suggests structural injury."),
        ("nerve impingement", "Nerve impingement may increase value because it supports objective neurologic involvement."),
        ("radiculopathy", "Radiculopathy is significant because it supports radiating nerve symptoms tied to objective findings."),
        ("fracture", "A fracture is a major objective injury and often increases claim value."),
        ("injection", "Injection treatment suggests more serious ongoing pain requiring interventional care."),
        ("surgical consultation", "A surgical consultation may support higher value because it suggests specialist-level concern."),
        ("surgery recommendation", "A surgery recommendation may strongly increase value due to seriousness and future care implications."),
        ("permanent", "Permanency language can support long-term impairment."),
        ("impairment", "Impairment language can support lasting functional loss.")
    ]

    for phrase, explanation in rules:
        if phrase == "fracture" and "no fracture" in lower:
            continue
        if phrase in lower:
            indicators.append({
                "indicator": phrase.title(),
                "why_significant": explanation
            })

    return indicators


def build_treatment_gaps(dates):
    if len(dates) <= 1:
        return "Insufficient records to identify a meaningful treatment gap."
    return "Treatment gaps could not yet be reliably determined from the currently uploaded records."


def build_facts_of_loss(text, loss_date):
    accident_blocks = extract_accident_blocks(text)
    if not accident_blocks:
        return ""

    chosen = clean_record_junk(accident_blocks[0])

    bad_med_terms = [
        "mri", "impression", "findings", "radiology", "therapy",
        "clinic", "hospital", "diagnosis", "treatment", "ligament"
    ]
    if any(term in chosen.lower() for term in bad_med_terms):
        return ""

    if len(chosen) > 500:
        chosen = chosen[:500].rsplit(" ", 1)[0].strip()

    if loss_date and loss_date not in chosen:
        return f"On or about {loss_date}, our client was involved in a motor vehicle collision caused by the negligence of the at-fault driver. {sentence_case_fix(chosen)}"
    return sentence_case_fix(chosen)


def build_liability_section(facts_of_loss):
    facts = clean_text(facts_of_loss)
    if not facts:
        return ""

    lower = facts.lower()

    if any(term in lower for term in ["rear-end", "rear ended", "rear-ended", "struck from behind", "hit from behind"]):
        return (
            "Liability is clear. Our client was lawfully operating their vehicle when they were rear-ended by the at-fault driver. "
            "The duty to maintain a safe following distance and keep a proper lookout rests with the trailing vehicle. "
            "The collision was caused by the negligence of the at-fault driver, and our client did nothing to contribute to this crash."
        )

    if any(term in lower for term in ["failed to yield", "failure to yield", "did not yield"]):
        return (
            "Liability is clear. The at-fault driver failed to yield the right-of-way and caused this collision. "
            "Drivers have a duty to yield when required and operate their vehicles with reasonable care. "
            "The available facts support that the at-fault driver's negligence was the direct and proximate cause of this crash."
        )

    if any(term in lower for term in ["red light", "ran the light", "ran a red light", "stop sign"]):
        return (
            "Liability is clear. The at-fault driver failed to obey traffic control devices and caused this collision. "
            "Drivers must stop and yield as required by roadway controls. "
            "The crash occurred because the at-fault driver breached that duty, and our client was not comparatively at fault."
        )

    if any(term in lower for term in ["lane change", "unsafe lane change", "merged into", "changed lanes into"]):
        return (
            "Liability is clear. The at-fault driver made an unsafe lane change and collided with our client's vehicle. "
            "Motorists must ensure that any lane movement can be made safely before changing lanes. "
            "The at-fault driver's failure to do so directly caused this collision."
        )

    return (
        "Liability rests with the at-fault driver. Based on the facts of loss, the collision occurred because the at-fault driver "
        "failed to operate their vehicle safely and with proper regard for surrounding traffic conditions. "
        "Our client was not responsible for causing this crash, and the available facts support that the at-fault driver's negligence "
        "was the direct and proximate cause of the collision and resulting damages."
    )


def build_clean_treatment_summary(client_name, provider_name, provider_type, dates, complaints, impression, objective_findings, exam):
    patient_ref = client_name if client_name else "the patient"
    parts = []

    if complaints:
        if len(complaints) == 1:
            complaint_text = complaints[0]
        elif len(complaints) == 2:
            complaint_text = f"{complaints[0]} and {complaints[1]}"
        else:
            complaint_text = ", ".join(complaints[:-1]) + f", and {complaints[-1]}"
        parts.append(f"Following the collision, {patient_ref} reported {complaint_text}.")

    if provider_name:
        sentence = f"{patient_ref} sought evaluation and treatment"
        if dates and dates[0]:
            sentence += f" on {dates[0]}"
        sentence += f" with {provider_name}."
        parts.append(sentence)

    if exam:
        parts.append(f"Diagnostic imaging included {exam.title()}.")

    clean_impression = summarize_impression(impression)
    if clean_impression:
        parts.append(f"Imaging showed {clean_impression}.")

    cleaned_findings = []
    for item in objective_findings:
        low = item.lower()
        if "no fracture" in low or "no dislocation" in low or "unremarkable" in low:
            continue
        cleaned_findings.append(clean_record_junk(item))

    if cleaned_findings:
        joined = "; ".join(cleaned_findings[:2])
        parts.append(f"Objective findings included {joined}.")

    if not parts:
        if provider_name:
            return f"{patient_ref} sought medical evaluation and treatment following the collision with {provider_name}."
        return f"{patient_ref} sought medical evaluation and treatment following the collision."

    return " ".join([p for p in parts if p]).strip()


def build_demand_treatment_section(client_name, chronology, imaging_summary, objective_findings, complaints=None):
    patient_ref = client_name if client_name else "our client"
    parts = []

    if complaints:
        if len(complaints) == 1:
            ctext = complaints[0]
        elif len(complaints) == 2:
            ctext = f"{complaints[0]} and {complaints[1]}"
        else:
            ctext = ", ".join(complaints[:-1]) + f", and {complaints[-1]}"
        parts.append(f"Following the collision, {patient_ref} reported {ctext}.")

    if chronology:
        first = chronology[0]
        provider = first.get("provider", "")
        date = first.get("date_of_service", "")

        if provider and date:
            parts.append(f"{patient_ref} presented to {provider} on {date} for evaluation and treatment.")
        elif provider:
            parts.append(f"{patient_ref} presented to {provider} for evaluation and treatment.")

    first_img = imaging_summary[0] if imaging_summary else {}
    study = clean_record_junk(first_img.get("study", ""))
    impression = summarize_impression(first_img.get("impression_verbatim", ""))

    if study:
        parts.append(f"The diagnostic workup included {study.title()}.")
    if impression:
        parts.append(f"Imaging showed {impression}.")

    cleaned_findings = []
    for item in objective_findings:
        low = item.lower()
        if "no fracture" in low or "no dislocation" in low or "unremarkable" in low:
            continue
        cleaned = clean_record_junk(item)
        if cleaned:
            cleaned_findings.append(cleaned)

    if cleaned_findings:
        parts.append(f"Objective findings included {'; '.join(cleaned_findings[:2])}.")

    parts.append("These records support injury-related complaints, treatment, and diagnostic evaluation following the collision.")
    return " ".join([p for p in parts if p]).strip()


# -----------------------------
# Review text builder
# -----------------------------
def build_nice_review(data):
    analysis = data["medical_analysis"]

    provider_lines = []
    for item in analysis["provider_list"]:
        provider_type = f" ({item['provider_type']})" if item.get("provider_type") else ""
        date_range = f" — {item['date_range']}" if item.get("date_range") else ""
        provider_lines.append(f"{item['provider_name']}{provider_type}{date_range}")

    chronology_lines = []
    for row in analysis["chronology"]:
        pieces = []
        if row.get("date_of_service"):
            pieces.append(row.get("date_of_service"))
        if row.get("provider"):
            pieces.append(row.get("provider"))
        if row.get("chief_complaints"):
            pieces.append(f"Complaints: {row.get('chief_complaints')}")
        if row.get("diagnoses"):
            pieces.append(f"Impression: {row.get('diagnoses')}")
        if row.get("treatment_performed"):
            pieces.append(f"Study: {row.get('treatment_performed')}")
        chronology_lines.append(" | ".join(pieces))

    imaging_lines = []
    for row in analysis["imaging_summary"]:
        pieces = []
        if row.get("date"):
            pieces.append(row.get("date"))
        if row.get("study"):
            pieces.append(row.get("study"))
        if row.get("body_region"):
            pieces.append(row.get("body_region"))
        if row.get("impression_verbatim"):
            pieces.append(f"Impression: {row.get('impression_verbatim')}")
        imaging_lines.append(" | ".join(pieces))

    high_value_lines = []
    for row in analysis["high_value_indicators"]:
        high_value_lines.append(f"{row['indicator']}: {row['why_significant']}")

    return {
        "client_name": data.get("client_name", ""),
        "claim_number": data.get("claim_number", ""),
        "loss_date": data.get("loss_date", ""),
        "facts_of_loss": data.get("facts_of_loss", ""),
        "treatment_summary": data.get("treatment_summary", ""),
        "providers_text": "\n".join(provider_lines),
        "chronology_text": "\n".join(chronology_lines),
        "objective_findings_text": "\n".join(analysis["objective_findings"]),
        "imaging_summary_text": "\n".join(imaging_lines),
        "high_value_text": "\n".join(high_value_lines),
        "treatment_gaps": analysis["treatment_gaps"],
        "demand_treatment_section": analysis["demand_treatment_section"],
        "providers": data.get("providers", [])
    }


# -----------------------------
# Main extraction
# -----------------------------
def simple_extract_data(text):
    text = clean_text(text)

    client_name = find_client_name(text)
    claim_number = find_claim_number(text)
    loss_date = find_loss_date(text)

    service_date = find_service_date(text)
    all_dates = find_all_dates(text)
    if service_date:
        all_dates = [service_date] + [d for d in all_dates if d != service_date]

    provider_name = pick_best_provider_name(text)
    provider_type = find_provider_type(provider_name)

    impression = find_impression(text)
    exam = find_exam_type(text)
    complaints = extract_complaints(text)

    provider_list = build_provider_list(provider_name, provider_type, all_dates)
    chronology = build_chronology(provider_name, text, all_dates)
    objective_findings = find_objective_findings(text)
    imaging_summary = build_imaging_summary(text, provider_name, all_dates, impression)
    high_value_indicators = find_high_value_indicators(text)
    treatment_gaps = build_treatment_gaps(all_dates)

    facts_of_loss = build_facts_of_loss(text, loss_date)

    clean_treatment_summary = build_clean_treatment_summary(
        client_name=client_name,
        provider_name=provider_name,
        provider_type=provider_type,
        dates=all_dates,
        complaints=complaints,
        impression=impression,
        objective_findings=objective_findings,
        exam=exam
    )

    demand_treatment_section = build_demand_treatment_section(
        client_name=client_name,
        chronology=chronology,
        imaging_summary=imaging_summary,
        objective_findings=objective_findings,
        complaints=complaints
    )

    providers_for_form = []
    if provider_name:
        providers_for_form.append({
            "name": provider_name,
            "amount": ""
        })

    data = {
        "client_name": client_name,
        "claim_number": claim_number,
        "loss_date": loss_date,
        "facts_of_loss": facts_of_loss,
        "treatment_summary": clean_treatment_summary,
        "providers": providers_for_form,
        "medical_analysis": {
            "provider_list": provider_list,
            "chronology": chronology,
            "objective_findings": objective_findings,
            "imaging_summary": imaging_summary,
            "high_value_indicators": high_value_indicators,
            "treatment_gaps": treatment_gaps,
            "demand_treatment_section": demand_treatment_section
        }
    }

    data["review"] = build_nice_review(data)
    return data
