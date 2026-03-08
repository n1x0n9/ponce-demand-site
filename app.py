from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for, session
from docx import Document
from docx.shared import Pt
import io
import re

app = Flask(__name__)
app.secret_key = "ponce_secret_key"
USERNAME = "admin"
PASSWORD = "ponce"


def clean_text(value):
    return (value or "").strip()


def clean_facts_of_loss(text):
    text = clean_text(text)
    replacements = {
        "client was client was": "client was",
        "our client was client was": "our client was",
        "was was": "was",
        "the the": "the",
        "rear-ended from the rear": "rear-ended",
        "collision collision": "collision",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
        text = text.replace(bad.title(), good.title())
    return " ".join(text.split())


def parse_money(value):
    value = clean_text(value).replace("$", "").replace(",", "")
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def money(value):
    return "${:,.2f}".format(value)


def safe_filename(value):
    value = clean_text(value)
    if not value:
        return "Demand_Letter"
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value)
    value = value.replace(" ", "_")
    return value or "Demand_Letter"


def add_paragraph(document, text="", bold=False, font_size=11, space_after=8):
    p = document.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.font.name = "Times New Roman"
    run.font.size = Pt(font_size)
    p.paragraph_format.space_after = Pt(space_after)
    return p


def build_letter_data(form):
    recipient_name = clean_text(form.get("recipient_name"))
    adjuster_name = clean_text(form.get("adjuster_name"))
    client_name = clean_text(form.get("client_name"))
    claim_number = clean_text(form.get("claim_number"))
    loss_date = clean_text(form.get("loss_date"))
    deadline = clean_text(form.get("deadline"))

    facts_of_loss = clean_facts_of_loss(form.get("facts_of_loss"))
    treatment_text = clean_text(form.get("treatment_summary"))
    non_economic_text = clean_text(form.get("non_economic_damages"))
    damages_explanation = clean_text(form.get("damages_explanation"))

    provider_names = form.getlist("provider_name[]")
    provider_amounts = form.getlist("provider_amount[]")

    providers = []
    for name, amount in zip(provider_names, provider_amounts):
        clean_name = clean_text(name)
        clean_amount_raw = clean_text(amount)

        if not clean_name and not clean_amount_raw:
            continue

        try:
            clean_amount = float(clean_amount_raw) if clean_amount_raw else 0.0
        except ValueError:
            clean_amount = 0.0

        providers.append({
            "provider_name": clean_name or "Provider",
            "amount": clean_amount,
            "amount_display": money(clean_amount)
        })

    medical_expenses = parse_money(form.get("medical_expenses"))
    lost_wages = parse_money(form.get("lost_wages"))

    provider_total = sum(item["amount"] for item in providers)
    if provider_total > 0:
        medical_expenses = provider_total

    multiplier_value = clean_text(form.get("multiplier"))
    try:
        multiplier_num = float(multiplier_value) if multiplier_value else 3.0
    except ValueError:
        multiplier_num = 3.0

    economic_total = medical_expenses + lost_wages
    suggested_amount = economic_total * multiplier_num

    policy_limit_checked = form.get("policy_limit_demand") == "yes"

    if facts_of_loss:
        liability_text = (
            "Liability is clear in this matter. Based on the facts of loss, the collision was caused "
            "by the negligence of the at-fault driver, who failed to exercise ordinary care in the "
            "operation of the vehicle. As a direct and proximate result of that negligence, our client "
            "sustained injuries and damages."
        )
    else:
        liability_text = (
            "Liability is clear. The available facts show that the collision was caused by the negligence "
            "of the at-fault driver, who failed to operate the vehicle in a reasonably safe manner under "
            "the circumstances."
        )

    if policy_limit_checked:
        demand_type = "Policy Limits Demand"
        suggested_settlement_display = "Policy Limits"
        conclusion_text = (
            "Based on the clear liability of your insured, the nature and extent of our client's injuries, "
            "the medical treatment required, and the resulting damages, we hereby demand tender of all "
            "available policy limits within the time allowed."
        )
    else:
        demand_type = "Settlement Demand"
        suggested_settlement_display = money(suggested_amount)
        conclusion_text = (
            f"Based on the liability, injuries, treatment, economic losses, and non-economic damages, "
            f"we believe a fair and reasonable settlement of this claim is {suggested_settlement_display}."
        )

    return {
        "recipient_name": recipient_name,
        "adjuster_name": adjuster_name,
        "client_name": client_name,
        "claim_number": claim_number,
        "loss_date": loss_date,
        "deadline": deadline,
        "facts_of_loss": facts_of_loss,
        "liability_text": liability_text,
        "treatment_text": treatment_text,
        "non_economic_text": non_economic_text,
        "damages_explanation": damages_explanation,
        "providers": providers,
        "medical_expenses": medical_expenses,
        "lost_wages": lost_wages,
        "multiplier_num": multiplier_num,
        "economic_total": economic_total,
        "suggested_settlement_display": suggested_settlement_display,
        "policy_limit_checked": policy_limit_checked,
        "demand_type": demand_type,
        "conclusion_text": conclusion_text,
    }


def build_docx(letter_data):
    document = Document()

    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)

    add_paragraph(
        document,
        "This letter is written for the sole purpose of settlement and is not intended for use for any other purpose without the express written consent of this office. Accordingly, this letter and the material included herein shall not, to the extent allowed by law, be admitted as evidence.",
        font_size=11,
        space_after=12
    )

    recipient_line = (
        letter_data["recipient_name"]
        or letter_data["adjuster_name"]
        or "Adjuster"
    )
    add_paragraph(document, f"Dear {recipient_line}:", font_size=11, space_after=12)

    intro = (
        f"Texas Ponce Law, PLLC has been retained to represent {letter_data['client_name'] or 'our client'} "
        f"for injuries sustained as a result of a motor vehicle collision that occurred on "
        f"{letter_data['loss_date'] or 'the date of loss'}."
    )
    add_paragraph(document, intro, font_size=11, space_after=12)

    if letter_data["claim_number"]:
        add_paragraph(document, f"Claim Number: {letter_data['claim_number']}", font_size=11, space_after=12)

    if letter_data["deadline"]:
        add_paragraph(document, f"Demand Deadline: {letter_data['deadline']}", font_size=11, space_after=12)

    add_paragraph(document, "Facts of Loss", bold=True, font_size=12, space_after=6)
    add_paragraph(document, letter_data["facts_of_loss"] or "N/A", font_size=11, space_after=12)

    add_paragraph(document, "Liability", bold=True, font_size=12, space_after=6)
    add_paragraph(document, letter_data["liability_text"], font_size=11, space_after=12)

    add_paragraph(document, "Treatment and Injuries", bold=True, font_size=12, space_after=6)
    add_paragraph(document, letter_data["treatment_text"] or "N/A", font_size=11, space_after=12)

    add_paragraph(document, "Non-Economic Damages", bold=True, font_size=12, space_after=6)
    add_paragraph(document, letter_data["non_economic_text"] or "N/A", font_size=11, space_after=12)

    add_paragraph(document, "Medical Bills", bold=True, font_size=12, space_after=6)
    if letter_data["providers"]:
        for provider in letter_data["providers"]:
            add_paragraph(
                document,
                f"{provider['provider_name']}: {provider['amount_display']}",
                font_size=11,
                space_after=4
            )
    else:
        add_paragraph(document, "No provider bills listed.", font_size=11, space_after=8)

    add_paragraph(document, "", font_size=11, space_after=2)
    add_paragraph(document, f"Medical Expenses: {money(letter_data['medical_expenses'])}", font_size=11, space_after=4)
    add_paragraph(document, f"Lost Wages: {money(letter_data['lost_wages'])}", font_size=11, space_after=4)
    add_paragraph(document, f"Multiplier: {letter_data['multiplier_num']:.1f}", font_size=11, space_after=4)
    add_paragraph(document, f"Suggested Settlement: {letter_data['suggested_settlement_display']}", font_size=11, space_after=12)

    add_paragraph(document, "Damages Explanation", bold=True, font_size=12, space_after=6)
    add_paragraph(document, letter_data["damages_explanation"] or "N/A", font_size=11, space_after=12)

    add_paragraph(document, "Conclusion", bold=True, font_size=12, space_after=6)
    add_paragraph(document, letter_data["conclusion_text"], font_size=11, space_after=12)

    add_paragraph(document, "Please contact our office if you have any questions.", font_size=11, space_after=12)

    add_paragraph(document, "Sincerely,", font_size=11, space_after=18)
    add_paragraph(document, "Texas Ponce Law, PLLC", font_size=11, space_after=0)

    return document

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            error = "Invalid login credentials"

    return render_template("login.html", error=error)

@app.route("/", methods=["GET"])
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    return render_template("form.html")

@app.route("/generate", methods=["POST"])
def generate():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    letter_data = build_letter_data(request.form)
    document = build_docx(letter_data)

    file_stream = io.BytesIO()
    document.save(file_stream)
    file_stream.seek(0)

    demand_label = "Policy_Limits_Demand" if letter_data["policy_limit_checked"] else "Settlement_Demand"
    client_part = safe_filename(letter_data["client_name"] or "Client")
    filename = f"{client_part}_{demand_label}.docx"

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@app.route("/preview-data", methods=["POST"])
def preview_data():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    letter_data = build_letter_data(request.form)
    return jsonify({
        "demand_type": letter_data["demand_type"],
        "medical_expenses": money(letter_data["medical_expenses"]),
        "lost_wages": money(letter_data["lost_wages"]),
        "suggested_settlement": letter_data["suggested_settlement_display"]
    })

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
if __name__ == "__main__":
    app.run(debug=True)
