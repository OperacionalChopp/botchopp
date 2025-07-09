type Entrada = {
  mensagem: string
  usuario?: string
  contexto?: string
}

type Saida = {
  resposta: string
}

export async function handleUserQuery(entrada: Entrada): Promise<Saida> {
  try {
    const respostaIA = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'meta-llama/llama-4-maverick:free',
        messages: [
          {
            role: 'system',
            content: `Você é o BotChopp, garçom virtual informal, espirituoso e simpático. Responda como se estivesse servindo um cliente no balcão de um boteco com humor e leveza.`
          },
          {
            role: 'user',
            content: entrada.mensagem
          }
        ]
      })
    })

    const dados = await respostaIA.json()
    const texto = dados.choices?.[0]?.message?.content || 'Tive um branco na espuma aqui... tenta de novo 🍻'

    return { resposta: texto }
  } catch (erro) {
    console.error('Erro ao chamar IA:', erro)
    return {
      resposta: 'Deu tilt na chopeira da IA 🧠🍺 tenta de novo em breve!'
    }
  }
}
