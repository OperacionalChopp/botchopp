from base_conhecimento.faq_data import faq_data

def test_responder_logic(user_text):
    texto_usuario = user_text.lower()
    matched_faqs = []

    for item in faq_data:
        found_keywords = []
        for palavra_chave in item["palavras_chave"]:
            if palavra_chave in texto_usuario:
                found_keywords.append(palavra_chave)
        
        if found_keywords:
            matched_faqs.append(item)
    
    print(f"Texto do usuário: '{user_text}'")
    print(f"FAQs encontradas ({len(matched_faqs)}):")
    for faq in matched_faqs:
        print(f"  - {faq['pergunta']}")
    
    if not matched_faqs:
        print("  -> Nenhuma FAQ encontrada.")
    elif len(matched_faqs) == 1:
        print(f"  -> Resposta direta: {matched_faqs[0]['resposta']}")
    else:
        print("  -> Múltiplas FAQs encontradas. Deveria mostrar botões.")
        for faq in matched_faqs:
            print(f"     Botão: {faq['pergunta']}")

# Testes
test_responder_logic("horário")
test_responder_logic("chopp")
test_responder_logic("qual o horário de funcionamento")
test_responder_logic("qual a validade do chopp")
test_responder_logic("olá")
test_responder_logic("pergunta aleatória")
```   Execute `python test_bot.py` no seu terminal. Isso vai te dar uma ideia de quais FAQs estão sendo encontradas para cada entrada.

**3. Se o problema for o `callback_data` (muito longo):**
Se os logs do Render mostrarem algo sobre `callback_data` ou se os botões não aparecerem no Telegram, podemos mudar a estratégia.

No `base_conhecimento/faq_data.py`, adicione um `id` único para cada FAQ:

```python
faq_data = [
    {
        "id": "boas_vindas", #
