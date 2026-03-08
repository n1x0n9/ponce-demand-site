from flask import Flask, render_template, request, send_file
from docx import Document
from pathlib import Path
import tempfile
import re

app = Flask(__name__)

USERNAME = "admin"
PASSWORD = "ponce"


def safe_filename(text):
    text = text.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_\-]", "", text) or "client"


def money(value):
    return f"${value:,.2f}"


def medical_total(bills):
    return sum(amount for _, amount in bills)


def build_facts_of_loss(location, client_action, defendant_action, point_of_impact, police_report, citation, witnesses):
    parts = []

    client_action = client_action.strip()
    defendant_action = defendant_action.strip()

    # cleaner opening so it doesn't do "our client was client was ..."
    sentence1 = "On the date of loss, our client "
    sentence1 += client_action

    if location:
        sentence1 += f" in the area of {location}"

    sentence1 += f" when the at-fault driver {defendant_action}."
    parts.append(sentence1)

    if point_of_impact:
        parts.append(
            f"The collision resulted in impact to the {point_of_impact} portion of our client's vehicle."
        )

    if police_report:
        parts.append("Law enforcement responded to the scene and a police report was generated.")

    if citation:
        parts.append("The at-fault driver was cited in connection with the collision.")

    if witnesses:
        parts.append("Witness information and surrounding circumstances further support our client's version of events.")

    return " ".join(parts).strip()


def build_liability(crash_type, police_report, citation):
    if crash_type == "rear_end":
        base = (
            "Liability is clear in this matter. Your insured failed to maintain a proper lookout, "
            "failed to control speed, and failed to stop in time to avoid striking our client's vehicle from the rear."
        )
    elif crash_type == "left_turn":
        base = (
            "Liability is clear in this matter. Your insured failed to yield the right-of-way while attempting a left turn "
            "and caused the collision made the basis of this claim."
        )
    elif crash_type == "lane_change":
        base = (
            "Liability is clear in this matter. Your insured made an unsafe lane change without first ensuring the lane was clear, "
            "thereby causing the collision."
        )
    elif crash_type == "red_light_stop_sign":
        base = (
            "Liability is clear in this matter. Your insured failed to obey a traffic control device and entered the intersection unsafely, "
            "thereby causing the collision."
        )
    elif crash_type == "failure_to_yield":
        base = (
            "Liability is clear in this matter. Your insured failed to yield the right-of-way and operated their vehicle in a negligent manner, "
            "causing this collision."
        )
    elif crash_type == "parking_lot_backing":
        base = (
            "Liability is clear in this matter. Your insured failed to ensure the path of travel was clear while backing or maneuvering in a parking area, "
            "thereby causing the collision."
        )
    else:
        base = (
            "Based on the facts described above, liability for this collision clearly rests with your insured. "
            "Your insured failed to operate their vehicle in a safe and prudent manner and failed to take reasonable steps to avoid the collision."
        )

    extras = []
    if police_report:
        extras.append("The existence of a police report further supports liability.")
    if citation:
        extras.append("The issuance of a citation to your insured is additional evidence of fault.")

    return " ".join([base] + extras).strip()


def build_treatment_narrative(client_name, symptoms, treatment_types, future_treatment, treatment_notes):
    pieces = [
        f"Immediately following the collision, {client_name} experienced {symptoms}.",
        f"Thereafter, {client_name} underwent treatment including {treatment_types}."
    ]

    if treatment_notes:
        pieces.append(treatment_notes)

    if future_treatment:
        pieces.append("Ongoing care and/or future treatment may be necessary as a result of the injuries sustained in this collision.")

    return " ".join(pieces).strip()


def build_non_economic_damages(client_name, pain, sleep, anxiety, chores, hobbies, family_impact, driving_fear, extra_notes):
    pieces = [
        f"As a result of the collision and resulting injuries, {client_name} has endured significant physical pain, emotional distress, and disruption to daily life."
    ]

    activity_parts = []
    if chores:
        activity_parts.append("household chores")
    if hobbies:
        activity_parts.append("recreational activities")
    if family_impact:
        activity_parts.append("normal family and personal activities")

    if activity_parts:
        pieces.append(
            "Activities that once were routine—including "
            + ", ".join(activity_parts)
            + "—now cause pain, difficulty, or require modification."
        )

    emotional_parts = []
    if anxiety:
        emotional_parts.append("anxiety")
    if sleep:
        emotional_parts.append("disrupted sleep")
    if driving_fear:
        emotional_parts.append("apprehension while driving")

    if emotional_parts:
        pieces.append(
            "Additionally, the traumatic nature of the collision has caused "
            + ", ".join(emotional_parts)
            + "."
        )

    if pain:
        pieces.append("These injuries have caused ongoing pain and discomfort that interfere with normal daily functioning.")

    pieces.append(f"These ongoing limitations have reduced {client_name}'s quality of life and ability to engage in normal activities.")

    if extra_notes:
        pieces.append(extra_notes)

    return " ".join(pieces).strip()


def replace_text_in_doc(doc, replacements):
    for p in doc.paragraphs:
        for key, val in replacements.items():
            if key in p.text:
                p.text = p.text.replace(key, val)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for key, val in replacements.items():
                        if key in p.text:
                            p.text = p.text.replace(key, val)


def clean_template(doc):
    remove_contains = [
        "Write a case-specific narrative describing how the collision occurred",
        "Write a case-specific liability section",
        "Create a Non-Economic Damages section",
        "Create table based on the medical bills provided",
        "It will look something like this",
        "Based on the facts described above, liability for this collision rests with your insured."
    ]

    exact_remove = {
        "[PROVIDER NAME]",
        "$ [AMOUNT]",
    }

    for p in doc.paragraphs:
        text = p.text.strip()

        if text in exact_remove:
            p.text = ""
            continue

        for snippet in remove_contains:
            if snippet in text:
                p.text = ""
                break


def insert_medical_table(doc, bills):
    for table in doc.tables:
        if not table.rows:
            continue

        header_cells = table.rows[0].cells
        if len(header_cells) < 2:
            continue

        left = header_cells[0].text.strip().lower()
        right = header_cells[1].text.strip().lower()

        if "provider" in left and "amount" in right:
            while len(table.rows) > 1:
                table._element.remove(table.rows[1]._element)

            total = 0.0
            for provider, amount in bills:
                row = table.add_row().cells
                row[0].text = provider
                row[1].text = money(amount)
                total += amount

            total_row = table.add_row().cells
            total_row[0].text = "TOTAL"
            total_row[1].text = money(total)
            break


def suggest_settlement(med_total, lost_wages, multiplier):
    base = med_total + lost_wages
    pain_component = med_total * multiplier
    return base + pain_component


def form_bool(name):
    return request.form.get(name) == "yes"


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == USERNAME and request.form.get("password") == PASSWORD:
            return render_template("form.html")
    return render_template("login.html")


@app.route("/generate", methods=["POST"])
def generate():
    adjuster_name = request.form.get("adjuster_name", "").strip()
    client_name = request.form.get("client_name", "").strip()
    collision_date = request.form.get("collision_date", "").strip()
    deadline = request.form.get("deadline", "").strip()

    crash_type = request.form.get("crash_type", "other").strip()
    location = request.form.get("location", "").strip()
    client_action = request.form.get("client_action", "").strip()
    defendant_action = request.form.get("defendant_action", "").strip()
    point_of_impact = request.form.get("point_of_impact", "").strip()

    police_report = form_bool("police_report")
    citation = form_bool("citation")
    witnesses = form_bool("witnesses")

    symptoms = request.form.get("symptoms", "").strip()
    treatment_types = request.form.get("treatment_types", "").strip()
    future_treatment = form_bool("future_treatment")
    treatment_notes = request.form.get("treatment_notes", "").strip()

    lost_wages_raw = request.form.get("lost_wages", "0").replace("$", "").replace(",", "").strip()
    multiplier_raw = request.form.get("multiplier", "0").strip()
    settlement_raw = request.form.get("settlement_amount", "").replace("$", "").replace(",", "").strip()
    policy_limit_raw = request.form.get("policy_limit_amount", "").replace("$", "").replace(",", "").strip()

    try:
        lost_wages = float(lost_wages_raw) if lost_wages_raw else 0.0
    except ValueError:
        lost_wages = 0.0

    try:
        multiplier = float(multiplier_raw) if multiplier_raw else 0.0
    except ValueError:
        multiplier = 0.0

    provider_names = request.form.getlist("provider_name")
    provider_amounts = request.form.getlist("provider_amount")

    bills = []
    for provider, amount in zip(provider_names, provider_amounts):
        provider = provider.strip()
        amount = amount.replace("$", "").replace(",", "").strip()

        if not provider:
            continue

        try:
            amount_value = float(amount) if amount else 0.0
        except ValueError:
            amount_value = 0.0

        bills.append((provider, amount_value))

    med_total = medical_total(bills)

    pain = form_bool("pain")
    sleep = form_bool("sleep")
    anxiety = form_bool("anxiety")
    chores = form_bool("chores")
    hobbies = form_bool("hobbies")
    family_impact = form_bool("family_impact")
    driving_fear = form_bool("driving_fear")
    non_econ_extra = request.form.get("non_econ_extra", "").strip()

    use_suggestion = form_bool("use_suggestion")
    policy_limit_demand = form_bool("policy_limit_demand")

    if policy_limit_demand:
        try:
            settlement_amount = float(policy_limit_raw) if policy_limit_raw else 0.0
        except ValueError:
            settlement_amount = 0.0
    elif use_suggestion and multiplier > 0:
        settlement_amount = suggest_settlement(med_total, lost_wages, multiplier)
    else:
        try:
            settlement_amount = float(settlement_raw) if settlement_raw else 0.0
        except ValueError:
            settlement_amount = 0.0

    facts_of_loss = build_facts_of_loss(
        location=location,
        client_action=client_action,
        defendant_action=defendant_action,
        point_of_impact=point_of_impact,
        police_report=police_report,
        citation=citation,
        witnesses=witnesses,
    )

    liability = build_liability(crash_type, police_report, citation)

    treatment_narrative = build_treatment_narrative(
        client_name=client_name,
        symptoms=symptoms,
        treatment_types=treatment_types,
        future_treatment=future_treatment,
        treatment_notes=treatment_notes,
    )

    non_economic_damages = build_non_economic_damages(
        client_name=client_name,
        pain=pain,
        sleep=sleep,
        anxiety=anxiety,
        chores=chores,
        hobbies=hobbies,
        family_impact=family_impact,
        driving_fear=driving_fear,
        extra_notes=non_econ_extra,
    )

    template_path = Path("templates_docx") / "Demand Template.docx"
    if not template_path.exists():
        return f"Template not found: {template_path}", 500

    doc = Document(str(template_path))

    conclusion_text = (
        "Based on the clear liability of your insured, the severity of the collision, the objective diagnostic findings, "
        f"and the ongoing impact on {client_name}'s quality of life, we hereby demand {money(settlement_amount)} "
        "in full and final settlement of this claim."
    )

    replacements = {
        "[ADJUSTER NAME]": adjuster_name,
        "[CLIENT NAME]": client_name,
        "[DATE]": collision_date,
        "[DEMAND DEADLINE DATE AND TIME]": deadline,
        "[DATE AND TIME]": deadline,
        "[INSERT FACTS OF LOSS HERE]": facts_of_loss,
        "(Write a case-specific liability section based on the facts of loss)": liability,
        "[Insert treatment narrative based on the treatment summary]": treatment_narrative,
        "[Create a Non-Economic Damages section based on information the attorney will input about the client]": non_economic_damages,
        "[SETTLEMENT AMOUNT]": money(settlement_amount),
        "TOTAL MEDICAL EXPENSES: $ [TOTAL]": f"TOTAL MEDICAL EXPENSES: {money(med_total)}",
        "[TOTAL]": money(med_total),
        "Based on:\n• the clear liability of your insured\n• the severity of the collision\n• the objective diagnostic findings\n• the ongoing impact on my client's quality of life": conclusion_text,
    }

    replace_text_in_doc(doc, replacements)
    clean_template(doc)
    insert_medical_table(doc, bills)

    # extra cleanup in case the conclusion bullets remain as separate paragraphs
    for p in doc.paragraphs:
        t = p.text.strip()
        if t in {
            "Based on:",
            "• the clear liability of your insured",
            "• the severity of the collision",
            "• the objective diagnostic findings",
            "• the ongoing impact on my client's quality of life",
        }:
            p.text = ""

    case_folder = f"{safe_filename(client_name)}_{collision_date.replace('/', '-')}"
    output_name = f"{case_folder}_Demand_Letter.docx"

    temp_dir = tempfile.gettempdir()
    output_path = Path(temp_dir) / output_name
    doc.save(str(output_path))

    return send_file(str(output_path), as_attachment=True, download_name=output_name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
