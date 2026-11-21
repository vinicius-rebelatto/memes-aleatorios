# 🤖 Memes Aleatórios

Automação que posta memes no canal `#memes-aleatorios` do nosso Discord, com votação e **Meme da Semana**.
Roda de graça no GitHub Actions: não tem servidor, nem nada ligado o tempo todo.

## Como funciona

- **3 vezes por dia** (11h17, 16h17 e 21h17), o bot sorteia uma fonte (r/eu_nvr, r/DiretoDoZapZap ou r/me_irl),
  pega os memes recentes, descarta NSFW, spoilers e o que já saiu, e posta **o mais votado**. É assim que o
  assunto do momento aparece sozinho. De vez em quando (20%) ele posta do [estoque da galera](#-estoque-da-galera).
- Cada meme já chega com duas reações:
  - 😂 **vota** no Meme da Semana;
  - 🚫 **passou do ponto**: quando **3 pessoas** marcam, o bot apaga o meme (ele confere de hora em hora).
- **Domingo às 21h07**, o bot anuncia o 🏆 **Meme da Semana** com o pódio. Memes que a galera posta no canal
  também concorrem.
- O que já foi postado fica em `dados/historico.json`. O bot atualiza esse arquivo sozinho, e é por isso que meme
  não repete.

## Instalação (uma vez só, uns 10 minutos)

### 1. Criar o bot no Discord

1. Entre em <https://discord.com/developers/applications> e clique em **New Application**. Dê um nome (ex.: `Memeiro`).
2. Em **General Information**, copie o **Application ID**: ele vai ser usado no passo 2. Aqui também dá para pôr a
   foto do bot em **App Icon**.
3. No menu **Bot**, clique em **Reset Token**, confirme e **copie o token**. Ele só aparece uma vez.

> ⚠️ O token é a senha do bot. Não mande no grupo e não cole no código: ele só vai nos secrets do GitHub (passo 4).
> Não precisa ligar nenhum *Privileged Gateway Intent*.

### 2. Convidar o bot para o servidor

Abra este link trocando `SEU_APPLICATION_ID` pelo ID do passo 1:

```
https://discord.com/oauth2/authorize?client_id=SEU_APPLICATION_ID&scope=bot&permissions=117824
```

Escolha o servidor e clique em **Autorizar**. O link já pede só o que o bot usa: ver canais, enviar mensagens,
inserir links, anexar arquivos, adicionar reações e ver o histórico de mensagens.

### 3. Pegar o ID do canal

No Discord: **Configurações de usuário → Avançado →** ative o **Modo desenvolvedor**. Depois clique com o botão
direito no `#memes-aleatorios` → **Copiar ID do canal**.

### 4. Colocar os segredos no GitHub

Neste repositório: **Settings → Secrets and variables → Actions → New repository secret**. Crie estes dois:

| Name                 | Secret                    |
| -------------------- | ------------------------- |
| `DISCORD_TOKEN`      | o token do passo 1        |
| `DISCORD_CHANNEL_ID` | o ID do canal do passo 3  |

### 5. Testar

Aba **Actions → Postar meme → Run workflow → Run workflow**. Em um minuto o meme aparece no canal. ✅

Pronto: daqui para frente é tudo automático. Para testar o Meme da Semana na hora, rode **Meme da Semana** do
mesmo jeito.

> 💡 Marcando **"Só simular"** antes de rodar o **Postar meme**, ele mostra no log qual meme seria postado, sem
> postar nada.

## Personalizar

| Quero mudar...                         | Onde                                                     |
| -------------------------------------- | -------------------------------------------------------- |
| Subreddits e o peso de cada um         | `config.yml` → `fontes`                                  |
| Quantos 🚫 apagam um meme              | `config.yml` → `moderacao.votos_para_remover`            |
| Emojis de voto e de "passou do ponto"  | `config.yml` → `votacao` e `moderacao`                   |
| Chance de postar do estoque            | `config.yml` → `estoque.chance`                          |
| Horários dos posts                     | `.github/workflows/postar-meme.yml` → `cron`             |
| Dia e hora do Meme da Semana           | `.github/workflows/meme-da-semana.yml` → `cron`          |

Dá para editar direto pelo site do GitHub (ícone de lápis no arquivo → **Commit changes**).

**Sobre os horários:** `cron: "17 11,16,21 * * *"` quer dizer "no minuto 17 das 11h, 16h e 21h, todo dia", e a
linha `timezone` mantém tudo no horário de Brasília. Exemplos:

- 4 posts por dia: `"17 10,14,18,22 * * *"`
- 2 posts por dia: `"17 12,20 * * *"`
- Meme da Semana na sexta às 18h: `"7 18 * * 5"` (0 = domingo, 1 = segunda, …, 6 = sábado)

O GitHub às vezes atrasa alguns minutos (em horário de pico, até meia hora). É normal.

## 📦 Estoque da galera

A pasta [`estoque/`](estoque/) guarda memes que a própria galera sobe. Para subir: abra a pasta →
**Add file → Upload files** → arraste as imagens → **Commit changes**.

- Formatos: `.jpg`, `.jpeg`, `.png`, `.gif` ou `.webp`, até 10 MB.
- Cada arquivo sai uma vez só.
- Para alguém conseguir subir, adicione a pessoa em **Settings → Collaborators → Add people**.

## Problemas comuns

O resultado de cada execução aparece na aba **Actions** (clique na execução para ver o log).

| Mensagem no log                                  | O que fazer                                                                                     |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| ⚠️ secrets ainda não foram configurados          | Faça o passo 4.                                                                                 |
| ❌ O token foi recusado                          | Gere outro token (passo 1) e atualize o secret `DISCORD_TOKEN`.                                 |
| ❌ O bot não consegue ver o canal / Falta permissão | Convide de novo com o link do passo 2. Se o canal ou a categoria for restrito, libere o cargo do bot nele. |
| ❌ Canal não encontrado                          | O `DISCORD_CHANNEL_ID` está errado: copie o ID de novo (passo 3).                               |
| ❌ Não achei nenhum meme novo                    | A meme-api pode estar fora do ar. Se continuar, adicione outro subreddit ou memes no estoque.   |

Também é normal:

- **O bot aparece offline** na lista de membros. Ele só "acorda" para postar.
- **Commits "🤖 Meme postado"** no histórico do repositório. É o bot salvando o que já postou.

## Rodar no computador (opcional)

```bash
pip install -r requirements-dev.txt
python -m bot.postar --simular   # mostra o próximo meme, sem mexer no Discord
python -m pytest                 # roda os testes
```

## Como o código está organizado

| Arquivo                | O que faz                                                            |
| ---------------------- | -------------------------------------------------------------------- |
| `bot/postar.py`        | Escolhe, posta, coloca as reações e salva no histórico               |
| `bot/moderar.py`       | Apaga os memes do bot que levaram 🚫 suficientes                     |
| `bot/ranking.py`       | Conta os 😂 da semana e anuncia o pódio                              |
| `bot/fontes.py`        | Busca memes na [meme-api](https://github.com/D3vd/Meme_Api) e no estoque |
| `bot/historico.py`     | Lê e grava `dados/historico.json`                                    |
| `bot/discord_api.py`   | Conversa com a API do Discord                                        |
| `bot/config.py`        | Lê o `config.yml` e os secrets                                       |
| `.github/workflows/`   | Os agendamentos: postar, moderar, Meme da Semana e testes            |
