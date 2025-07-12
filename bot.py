# ("7561248614:AAErBhdJ2untqbtF2YEaTIgOJexuKyhzgKg")
import os
from http import HTTPStatus
from flask import Flask, request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    CommandHandler
)
from base_conhecimento.faq_data import faq_data

# --- Configuração ---
TOKEN = os.environ.get("7561248614:AAErBhdJ2untqbtF2YEaTIgOJexuKyhzgKg")
PORT = int(os.environ.get("PORT", 8000))

# --- Lista de Regiões Atendidas ---
REGIOES_ATENDIDAS = [
    "agua quente", "aguas claras", "arniqueira", "brazlandia", "ceilandia",
    "gama", "guara", "nucleo bandeirante", "park way", "recanto das emas",
    "riacho fundo", "riacho fundo ii", "samambaia", "santa maria",
    "scia/estrutural", "sia", "sol nascente / por do sol", "taguatinga",
    "valparaiso de goias", "vicente pires"
]

# --- Lógica do Bot (Handlers) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_start = (
        "Olá! Tudo bem? Aqui é da equipe do Chopp Brahma Express de Águas Claras. "
        "Passando pra te mostrar como ficou fácil garantir seu chopp gelado, com desconto especial, "
        "entregue direto na sua casa!\n\n"
        "Já pensou em garantir seu Chopp Brahma com até 20% OFF, sem sair de casa? É só clicar:\n"
        "https://www.choppbrahmaexpress.com.br/chopps\n"
        "ou\n"
        "https://www.ze.delivery/produtos/categoria/chopp\n\n"
        "Aliás, você sabe tirar o chopp perfeito? Dá uma olhada nesse link "
        "https://l1nk.dev/sabe-tirar-o-chopp-perfeito e descubra como deixar seu chope ainda melhor!"
    )
    await update.message.reply_text(texto_start)

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text.lower()
    texto_normalizado = texto_usuario.replace('á', 'a').replace('â', 'a').replace('ã', 'a').replace('é', 'e').replace('ê', 'e').replace('í', 'i').replace('ó', 'o').replace('ô', 'o').replace('ú', 'u').replace('ç', 'c')

    contem_palavra_de_regiao = any(palavra in texto_normalizado for palavra in ["atende", "entrega", "regiao", "bairro", "cidade"])
    regiao_encontrada = None
    for regiao in REGIOES_ATENDIDAS:
        if regiao in texto_normalizado:
            regiao_encontrada = regiao
            break

    if contem_palavra_de_regiao and regiao_encontrada:
        await update.message.reply_text(
            f"Sim, atendemos em {regiao_encontrada.title()}! ✅\n"
            "Pode fazer seu pedido pelo site que entregamos aí."
        )
        return

    scored_faqs = []
    palavras_do_usuario = set(texto_usuario.split()) 
    for item in faq_data:
        palavras_chave_item = set(item["palavras_chave"])
        intersecao = palavras_do_usuario.intersection(palavras_chave_item)
        score = len(intersecao)
        if score > 0:
            scored_faqs.append({"faq": item, "score": score})

    scored_faqs.sort(key=lambda x: x["score"], reverse=True)

    if not scored_faqs:
        await update.message.reply_text(
            "Desculpe, não entendi. 🤔\n"
            "Você pode perguntar sobre horário, formas de pagamento, ou se atendemos em uma região específica."
        )
        return

    max_score = scored_faqs[0]["score"]
    top_matched_faqs = [s["faq"] for s in scored_faqs if s["score"] == max_score]

    if len(top_matched_faqs) == 1:
        await update.message.reply_text(top_matched_faqs[0]["resposta"])
    else:
        keyboard = []
        for faq in top_matched_faqs:
            keyboard.append([InlineKeyboardButton(faq["pergunta"], callback_data=f"faq_id_{faq['id']}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você procura?",
            reply_markup=reply_markup
        )

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    if callback_data.startswith("faq_id_"):
        faq_id_selecionado = int(callback_data[len("faq_id_"):])
        for item in faq_data:
            if item["id"] == faq_id_selecionado:
                await query.message.reply_text(text=item["resposta"])
                await query.edit_message_reply_markup(reply_markup=None)
                return
        await query.message.reply_text(text="Desculpe, não consegui encontrar a resposta para essa opção.")

# --- Configuração da Aplicação e Servidor ---
ptb = Application.builder().token(TOKEN).build()

ptb.add_handler(CommandHandler("start", start_command))
ptb.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder))
ptb.add_handler(CallbackQueryHandler(button_callback_handler))

flask_app = Flask(__name__)

@flask_app.route("/api/telegram/webhook", methods=["POST"])
def telegram_webhook():
    ptb.update_queue.put(Update.de_json(request.get_json(force=True), ptb.bot))
    return Response(status=HTTPStatus.OK)

@flask_app.route("/health", methods=["GET"])
def health_check():
    return "Bot is healthy and running!", HTTPStatus.OK

def main():
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/api/telegram/webhook"
    ptb.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
