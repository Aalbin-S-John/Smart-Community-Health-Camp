
from flask import Flask, redirect, url_for
from config import Config

from routes.auth import auth
from routes.dashboard import dashboard
from routes.camps import camps
from routes.doctors import doctors
from routes.patient_camps import patient_camps
from routes.doctor_work import doctor_work
from routes.reports import reports
# pyrefly: ignore [missing-import]
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)

app.config["SECRET_KEY"] = Config.SECRET_KEY or "dev-only-change-this"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

csrf = CSRFProtect(app)

# Register blueprints
app.register_blueprint(auth)
app.register_blueprint(dashboard)
app.register_blueprint(camps)
app.register_blueprint(doctors)
app.register_blueprint(patient_camps)
app.register_blueprint(doctor_work)
app.register_blueprint(reports)


@app.route("/")
def home():
    return redirect(url_for("auth.login"))


if __name__ == "__main__":
    app.run(debug=True)
