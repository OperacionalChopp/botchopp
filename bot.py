# bot.py (SUGESTÃO DE MODIFICAÇÃO PARA handle_message)

import os
import json
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- Carregar dados do FAQ ---
FAQ_DATA = {}
try:
    with open('faq_data.json', 'r', encoding='utf-8') as f:
        FAQ_DATA = json.load(f)
except FileNotFoundError:
    print("ERRO: faq_data.json não encontrado. Certifique-se de que o arquivo está na raiz do projeto.")
except json.JSONDecodeError:
    print("ERRO: faq_data.json com formato JSON inválido.")

# --- Seus handlers (comandos e mensagens) ---

async def start(update: Update, context):
    """Envia a mensagem de boas-vindas com botões."""
    welcome_entry = FAQ_DATA.get("1")
    if welcome_entry:
        introduction_message = welcome_entry["resposta"]

        keyboard = [
            [InlineKeyboardButton("📍 Onde fica a loja?", callback_data="onde_fica")],
            [InlineKeyboardButton("🕒 Qual nosso horário?", callback_data="horario")],
            [InlineKeyboardButton("🍔 Quero ver o cardápio", callback_data="cardapio")],
            [InlineKeyboardButton("🧠 Tirar uma dúvida com a IA", callback_data="duvida_ia")],
            [InlineKeyboardButton("📞 Falar com alguém", callback_data="falar_com_alguem")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(introduction_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text('Olá! Eu sou seu bot! Parece que a mensagem de boas-vindas não foi carregada corretamente. Por favor, verifique o arquivo FAQ.')

async def handle_message(update: Update, context):
    """
    Processa mensagens de texto (não comandos) e tenta encontrar respostas no FAQ.
    Se encontrar palavras-chave relevantes, pode apresentar botões de perguntas relacionadas.
    """
    user_text = update.message.text.lower()
    response_text = "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Por favor, tente reformular ou use os botões abaixo para explorar as opções."
    reply_markup = None
    
    # Lista para coletar IDs/perguntas de FAQs relacionadas que podem ser apresentadas em botões
    related_faq_buttons = []
    
    found_exact_match = False

    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": # Pula a FAQ de boas-vindas
            continue
        
        # Converte as palavras-chave para minúsculas para comparação
        entry_keywords = [kw.lower() for kw in entry.get("palavras_chave", [])]

        # Verifica se alguma palavra-chave da entrada está no texto do usuário
        matches = [kw for kw in entry_keywords if kw in user_text]
        
        if matches:
            # Se a resposta for para 'Falar com Alguém' (ID 6 no novo FAQ sugerido)
            if faq_id == "6": # Atualizado para ID 6 conforme seu FAQ_DATA.json sugerido
                response_text = entry["resposta"]
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
                found_exact_match = True
                break # Encerra o loop, pois uma ação específica foi tomada
            
            # Se a palavra-chave é muito específica e queremos dar a resposta direta
            # Você precisará definir o que é "específico" para o seu bot.
            # Ex: Se a pergunta do FAQ for "Qual o horário de funcionamento?" e o usuário digitar isso.
            # Ou se você quer que certas FAQs sempre deem resposta direta.
            # Por enquanto, vamos considerar que se achou uma palavra-chave, é uma resposta direta.
            
            # Se o texto do usuário contiver a pergunta exata do FAQ ou uma palavra-chave muito forte,
            # talvez queiramos dar a resposta direta e encerrar.
            # Exemplo (você pode ajustar esta lógica):
            if any(user_text == kw for kw in entry_keywords): # Se o input do usuário for IGUAL a uma palavra-chave
                response_text = entry["resposta"]
                found_exact_match = True
                break # Encerra o loop, achou um match exato
            
            # Se não for um match exato, mas tiver palavras-chave correspondentes,
            # adiciona para sugerir em botões, se não houver um match direto ainda.
            if not found_exact_match:
                related_faq_buttons.append([InlineKeyboardButton(entry["pergunta"], callback_data=entry["id"])])

    if found_exact_match:
        await update.message.reply_text(response_text, reply_markup=reply_markup)
    elif related_faq_buttons:
        # Se encontrou FAQs relacionadas mas não um match direto
        # Opcional: Adicionar uma mensagem introdutória para as opções
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você gostaria de saber?",
            reply_markup=InlineKeyboardMarkup(related_faq_buttons)
        )
    else:
        # Nenhuma palavra-chave encontrada, retorna a mensagem padrão
        await update.message.reply_text(response_text, reply_markup=reply_markup)

# ... (O resto do seu código main() e app = main() permanece o mesmo) ...
