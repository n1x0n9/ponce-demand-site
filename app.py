from flask import Flask, render_template, request

app = Flask(__name__)


def clean_text(value):
    return (value or "").strip()


def clean_facts_of_loss(text):
    text = clean_text(text)
    replacements = {
        "client was client was": "client was",
        "our client was client was": "our client was",
        "was was": "was",
        "the the": "the",
    }
    lowered = text
    for bad, good in replacements.items():
        lowered = lowered.replace(bad, good)
        lowered = lowered.replace(bad.title(), good.title())
    return lowered


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


def suggest_settlement(med_total, lost_wages, multiplier):
    base = med_total + lost_wages
    pain_component = med_total * multiplier
    return base + pain_component


@app.route("/", methods=["GET", "POST"])
def index():
    generated_letter = ""
    demand_preview = "Settlement Demand"
    suggested_settlement_display = ""
    settlement_amount_value = ""
    policy_limit_checked = False
    use_suggested_checked = False
    multiplier_value = ""
    med_total_value = ""
    lost_wages_value = ""

    form_data = {
        "recipient_name": "",
        "client_name": "",
        "loss_date": "",
        "demand_deadline": "",
        "facts_of_loss": "",
        "liability_text": "",
        "treatment_text": "",
        "non_economic_text": "",
    }

    if request.method == "POST":
        recipient_name = clean_text(request.form.get("recipient_name"))
        client_name = clean_text(request.form.get("client_name"))
        loss_date = clean_text(request.form.get("loss_date"))
        demand_deadline = clean_text(request.form.get("demand_deadline"))
        facts_of_loss = clean_facts_of_loss(request.form.get("facts_of_loss"))
        liability_text = clean_text(request.form.get("liability_text"))
        treatment_text = clean_text(request.form.get("treatment_text"))
        non_economic_text = clean_text(request.form.get("non_economic_text"))

        med_total_value = clean_text(request.form.get("medical_expenses"))
        lost_wages_value = clean_text(request.form.get("lost_wages"))
        multiplier_value = clean_text(request.form.get("multiplier"))
        settlement_amount_value = clean_text(request.form.get("settlement_amount"))

        policy_limit_checked = request.form.get("policy_limit_demand") == "on"
        use_suggested_checked = request.form.get("use_suggested_settlement") == "on"

        med_total = parse_money(med_total_value)
        lost_wages = parse_money(lost_wages_value)

        try:
            multiplier_num = float(multiplier_value) if multiplier_value else 0.0
        except ValueError:
            multiplier_num = 0.0

        suggested_amount = suggest_settlement(med_total, lost_wages, multiplier_num)
        if suggested_amount > 0:
            suggested_settlement_display = money(suggested_amount)

        if policy_limit_checked:
            demand_preview = "Policy Limits Demand"
            final_demand_sentence = (
                "Based on the clear liability of your insured, the severity of the collision, "
                "the objective diagnostic findings, and the ongoing impact on my client's quality of life, "
                "we hereby demand tender of all available policy limits in full and final settlement of this claim."
            )
        else:
            demand_preview = "Settlement Demand"

            if use_suggested_checked and suggested_amount > 0:
                settlement_amount_value = money(suggested_amount)

            if settlement_amount_value:
                final_demand_sentence = (
                    f"Based on the clear liability of your insured, the severity of the collision, "
                    f"the objective diagnostic findings, and the ongoing impact on my client's quality of life, "
                    f"we hereby demand {settlement_amount_value} in full and final settlement of this claim."
                )
            else:
                final_demand_sentence = (
                    "Based on the clear liability of your insured, the severity of the collision, "
                    "the objective diagnostic findings, and the ongoing impact on my client's quality of life, "
                    "we hereby demand a fair and reasonable settlement in full and final settlement of this claim."
                )

        generated_letter = f"""This letter is written for the sole purpose of settlement and is not intended for use for any other purpose without the express written consent of this office. Accordingly, this letter and the material included herein shall not, to the extent allowed by law, be admitted as evidence.

Dear {recipient_name}:

Texas Ponce Law, PLLC has been retained to represent {client_name} for injuries sustained as a result of a motor vehicle collision that occurred on {loss_date}.

We have been instructed to recover compensation for the debt owed and personal injuries sustained as a direct result of this collision.

This settlement offer is open until {demand_deadline}.

Enclosed for your review are my client’s medical records, bills, and supporting documentation.

FACTS OF LOSS

{facts_of_loss}

LIABILITY

{liability_text}

TREATMENT AND INJURIES

{treatment_text}

PAST MEDICAL EXPENSES

Total Medical Expenses: {money(med_total)}

NON-ECONOMIC DAMAGES

{non_economic_text}

CONCLUSION

{final_demand_sentence}

This offer will remain open until {demand_deadline}.

Sincerely,

Texas Ponce Law, PLLC
"""

        form_data = {
            "recipient_name": recipient_name,
            "client_name": client_name,
            "loss_date": loss_date,
            "demand_deadline": demand_deadline,
            "facts_of_loss": facts_of_loss,
            "liability_text": liability_text,
            "treatment_text": treatment_text,
            "non_economic_text": non_economic_text,
        }

    return render_template(
        "form.html",
        generated_letter=generated_letter,
        demand_preview=demand_preview,
        suggested_settlement_display=suggested_settlement_display,
        settlement_amount_value=settlement_amount_value,
        policy_limit_checked=policy_limit_checked,
        use_suggested_checked=use_suggested_checked,
        multiplier_value=multiplier_value,
        med_total_value=med_total_value,
        lost_wages_value=lost_wages_value,
        form_data=form_data,
    )


if __name__ == "__main__":
    app.run(debug=True)
