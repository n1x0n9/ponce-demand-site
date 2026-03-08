from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():

    generated_letter = ""
    demand_type = "Settlement Demand"

    if request.method == "POST":

        recipient_name = request.form.get("recipient_name", "")
        client_name = request.form.get("client_name", "")
        loss_date = request.form.get("loss_date", "")

        policy_limit_demand = request.form.get("policy_limit_demand") == "on"
        settlement_amount = request.form.get("settlement_amount", "")

        if policy_limit_demand:
            demand_type = "Policy Limits Demand"
            demand_sentence = "we hereby demand tender of all available policy limits in full and final settlement of this claim."
        else:
            demand_type = "Settlement Demand"

            if settlement_amount:
                demand_sentence = f"we hereby demand the amount of {settlement_amount} in full and final settlement of this claim."
            else:
                demand_sentence = "we hereby demand a fair and reasonable settlement in full and final settlement of this claim."

        generated_letter = f"""
This letter is written for the sole purpose of settlement and is not intended for use for any other purpose without the express written consent of this office. Accordingly, this letter and the material included herein shall not, to the extent allowed by law, be admitted as evidence.

Dear {recipient_name}:

Texas Ponce Law, PLLC has been retained to represent {client_name} for injuries sustained as a result of a motor vehicle collision that occurred on {loss_date}.

We have been instructed to make demand upon your insured for the injuries and damages sustained by our client. Therefore, {demand_sentence}

Please contact our office if you have any questions.

Sincerely,

Texas Ponce Law, PLLC
"""

    return render_template(
        "form.html",
        generated_letter=generated_letter,
        demand_type=demand_type
    )


if __name__ == "__main__":
    app.run(debug=True)
