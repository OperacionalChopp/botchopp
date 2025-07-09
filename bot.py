from flask import Flask, request
import requests

TOKEN = "SEU_TOKEN_AQUI"  # Cole seu token do BotFather aqui
URL = f"https://api.telegram.org/bot{7561248614:AAHz-PCTNcgj5oyFei0PgNnmlwvSu4NSqfw}/"

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        send_message(chat_id, f"Você disse: {text}")
    return "ok"

def send_message(chat_id, text):
    url = URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

if __name__ == "__main__":
    app.run(debug=True)
