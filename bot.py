# bot.py (SUGESTÃO DE MODIFICAÇÃO PARA handle_message e handle_callback_query)

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
    
    found_exact_match = False # Flag para saber se já encontramos uma resposta direta

    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": # Pula a FAQ de boas-vindas
            continue
        
        # Converte as palavras-chave para minúsculas para comparação
        entry_keywords = [kw.lower() for kw in entry.get("palavras_chave", [])]

        # Verifica se alguma palavra-chave da entrada está no texto do usuário
        matches = [kw for kw in entry_keywords if kw in user_text]
        
        if matches:
            # Se a resposta for para 'Falar com Alguém' (ID 6 no novo FAQ sugerido)
            if faq_id == "6": 
                response_text = entry["resposta"]
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
                found_exact_match = True # Marca como match exato para sair do loop
                break 
            
            # Se o texto do usuário contiver a pergunta exata do FAQ ou uma palavra-chave muito forte,
            # ou se você deseja que esta entrada sempre dê uma resposta direta.
            # Você pode ajustar esta lógica para ser mais ou menos "exata".
            # Por exemplo, se user_text == "qual o horário de funcionamento" e 'horário de funcionamento' está em entry_keywords:
            if user_text in entry_keywords or any(user_text == kw for kw in entry_keywords): 
                response_text = entry["resposta"]
                found_exact_match = True
                break 
            
            # Se não for um match exato, mas encontrou palavras-chave, adiciona para sugerir em botões.
            # Adicionamos apenas se ainda não achamos um match exato.
            if not found_exact_match:
                related_faq_buttons.append([InlineKeyboardButton(entry["pergunta"], callback_data=faq_id)])

    if found_exact_match:
        # Se um match exato ou ação específica foi encontrada, envia a resposta.
        await update.message.reply_text(response_text, reply_markup=reply_markup)
    elif related_faq_buttons:
        # Se encontrou FAQs relacionadas (não um match exato), apresenta botões.
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você gostaria de saber?",
            reply_markup=InlineKeyboardMarkup(related_faq_buttons)
        )
    else:
        # Nenhuma palavra-chave encontrada, retorna a mensagem padrão.
        await update.message.reply_text(response_text, reply_markup=reply_markup)

async def handle_callback_query(update: Update, context):
    query = update.callback_query
    await query.answer()

    callback_data = query.data # Será o ID do FAQ (como string) ou a callback_data original ("onde_fica", "horario")
    
    response_text = "Desculpe, não consegui encontrar uma resposta para esta opção."
    reply_markup = None

    # Lógica para os botões fixos do /start
    if callback_data == "onde_fica":
        entry = FAQ_DATA.get("4") # Supondo que "4" seja o ID para "Onde fica a loja?"
        if entry:
            response_text = entry["resposta"]
    elif callback_data == "horario":
        entry = FAQ_DATA.get("3") # Supondo que "3" seja o ID para "Qual nosso horário?"
        if entry:
            response_text = entry["resposta"]
    elif callback_data == "cardapio":
        entry = FAQ_DATA.get("5") # Supondo que "5" seja o ID para "Quero ver o cardápio"
        if entry:
            response_text = entry["resposta"]
    elif callback_data == "duvida_ia":
        # Lógica para a dúvida com a IA, se for implementar uma integração específica
        response_text = "Para tirar dúvidas mais complexas, por favor, me diga sua pergunta e tentarei ajudar."
    elif callback_data == "falar_com_alguem":
        entry = FAQ_DATA.get("6") # Supondo que "6" seja o ID para "Falar com alguém"
        if entry:
            response_text = entry["resposta"]
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
            ])
    else:
        # Lógica para os botões gerados dinamicamente (com callback_data sendo o ID do FAQ)
        entry = FAQ_DATA.get(callback_data) 
        if entry:
            response_text = entry["resposta"]
            # Adicionar botões específicos se a resposta for do tipo 'Falar com alguém' (ID 6)
            if callback_data == "6": 
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])

    await query.edit_message_text(text=response_text
