import { handleUserQuery } from '@/lib/ia'

export async function POST(req: Request): Promise<Response> {
  try {
    const update = await req.json()

    const mensagem = update?.message?.text
    const nome = update?.message?.from?.first_name || 'CHOPPzeiro'
    const chatId = update?.message?.chat?.id

    if (!mensagem || !chatId) return new Response('mensagem ignorada')

    const { resposta } = await handleUserQuery({
      mensagem,
      usuario: nome,
      contexto: 'Mensagem via Telegram'
    })

    await fetch(`https://api.telegram.org/bot${process.env.BOT_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, text: resposta })
    })

    return new Response('ok')
  } catch (erro) {
    console.error('Erro ao processar mensagem do Telegram:', erro)
    return new Response('erro interno', { status: 500 })
  }
}
