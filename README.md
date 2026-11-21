# 🤖 Memes Aleatórios

Automação que posta memes no canal `#memes-aleatorios` do nosso Discord, com votação, **Meme da Semana** e um
**algoritmo da galera**: as reações de todo mundo decidem que tipo de meme vem depois.
Roda de graça no GitHub Actions: não tem servidor, nem nada ligado o tempo todo.

## Como funciona

**3 vezes por dia** (11h17, 16h17 e 21h17) o bot posta um meme, e cada meme chega com 4 reações:

| Reação | Significa         | O que muda                                                     |
| ------ | ----------------- | -------------------------------------------------------------- |
| 😂     | achei engraçado   | memes daquela fonte aparecem mais (e vale voto no Meme da Semana) |
| 😐     | sem graça         | memes daquela fonte aparecem menos                             |
| 🌶️     | quero mais pesado | a régua sobe                                                   |
| 🚫     | passou do ponto   | a régua desce, e com **3 pessoas** marcando o bot apaga o meme |

- **Domingo às 21h07** sai o 🏆 **Meme da Semana** com o pódio e o 🌡️ termômetro da galera. Memes que a galera
  posta no canal também concorrem.
- O bot confere os 🚫 de hora em hora, então meme que passou do ponto não fica muito tempo no ar.
- De vez em quando (20%) ele posta do [estoque da galera](#-estoque-da-galera).

### 🌡️ O algoritmo da galera

Cada fonte de memes (um subreddit) tem um **nível de peso**, de 1 (leve) a 5 (pesado):

| Nível | Fontes                        |
| ----- | ----------------------------- |
| 1     | r/wholesomememes              |
| 2     | r/DiretoDoZapZap              |
| 3     | r/HUEstation, r/me_irl        |
| 4     | r/eu_nvr                      |
| 5     | r/dankmemes                   |

- A **régua** começa no meio (3). Cada 🌶️ empurra ela um pouco pra cima e cada 🚫, pra baixo.
- Na hora de escolher, o bot prefere as fontes com nível **perto da régua** e com mais 😂 do que 😐.
- Dentro da fonte, ele pega o meme **mais votado entre os recentes**: post velho não ganha de post do momento.
- **1 em cada 5 posts é surpresa**: ignora a régua e sorteia qualquer fonte, para o algoritmo não ficar
  viciado e perceber quando o gosto da galera muda.
- A régua atual aparece no rodapé de cada meme (🌡️ régua 3,2/5) e no anúncio de domingo.

O estado do algoritmo fica em `dados/termometro.json` e o que já foi postado em `dados/historico.json`
(é por isso que meme não repete). O bot atualiza os dois sozinho.

### 🔞 NSFW

Memes marcados como NSFW no Reddit podem sair, contando como **um nível mais pesado** na régua: quanto mais
alta a régua, mais chance de aparecer. Mas o Discord só permite conteúdo adulto em canal marcado como
restrito por idade, então o bot **só posta NSFW se o canal estiver marcado assim**. Para ligar:
**Editar canal → Visão geral → Canal com restrição de idade**. Quem abrir o canal vai precisar confirmar que
tem 18 anos ou mais. Sem essa marcação, o bot simplesmente deixa os NSFW de fora.

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

No Discord, clique com o botão direito no `#memes-aleatorios` → **Copiar link**. O ID do canal é o último número
do link. (Ou ative **Configurações de usuário → Avançado → Modo desenvolvedor** e use **Copiar ID do canal**.)

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

> 💡 Marcando **"Só simular"** antes de rodar o **Postar meme**, ele testa todas as fontes e mostra no log qual
> meme seria postado, sem postar nada.

## Personalizar

| Quero mudar...                              | Onde                                                  |
| ------------------------------------------- | ----------------------------------------------------- |
| Fontes, o nível de cada uma e o peso        | `config.yml` → `fontes`                               |
| Os emojis das 4 reações                     | `config.yml` → `reacoes`                              |
| Onde a régua começa e a chance de surpresa  | `config.yml` → `termometro`                           |
| Liberar ou bloquear NSFW                    | `config.yml` → `nsfw.permitir`                        |
| Quantos 🚫 apagam um meme                   | `config.yml` → `moderacao.votos_para_remover`         |
| Chance de postar do estoque                 | `config.yml` → `estoque.chance`                       |
| Horários dos posts                          | `.github/workflows/postar-meme.yml` → `cron`          |
| Dia e hora do Meme da Semana                | `.github/workflows/meme-da-semana.yml` → `cron`       |

Dá para editar direto pelo site do GitHub (ícone de lápis no arquivo → **Commit changes**).

**Quer ir além do nível 5?** A régua só vai até a fonte mais pesada da lista: para memes mais pesados, adicione
fontes novas com nível 5 em `config.yml`. Rode o **Postar meme** com **"Só simular"** para ver se a fonte nova
funciona.

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
| ❌ Não achei nenhum meme novo                    | A meme-api pode estar fora do ar. Se continuar, adicione outra fonte ou memes no estoque.       |
| ℹ️ NSFW fica de fora                             | Normal: o canal não está marcado como restrito por idade (veja [NSFW](#-nsfw)).                 |

Também é normal:

- **O bot aparece offline** na lista de membros. Ele só "acorda" para postar.
- **Commits "🤖 Meme postado"** no histórico do repositório. É o bot salvando o que já postou e o termômetro.

## Rodar no computador (opcional)

```bash
pip install -r requirements-dev.txt
python -m bot.postar --simular   # testa as fontes e mostra o próximo meme, sem mexer no Discord
python -m pytest                 # roda os testes
```

## Como o código está organizado

| Arquivo                | O que faz                                                                    |
| ---------------------- | ---------------------------------------------------------------------------- |
| `bot/postar.py`        | Lê as reações, atualiza o termômetro, escolhe, posta e salva                 |
| `bot/termometro.py`    | O algoritmo da galera: régua de peso e afinidade de cada fonte               |
| `bot/fontes.py`        | Busca memes na [meme-api](https://github.com/D3vd/Meme_Api) e no estoque e escolhe o melhor |
| `bot/moderar.py`       | Apaga os memes do bot que levaram 🚫 suficientes                             |
| `bot/ranking.py`       | Conta os 😂 da semana e anuncia o pódio com o termômetro                     |
| `bot/historico.py`     | Lê e grava `dados/historico.json`                                            |
| `bot/discord_api.py`   | Conversa com a API do Discord                                                |
| `bot/config.py`        | Lê o `config.yml` e os secrets                                               |
| `.github/workflows/`   | Os agendamentos: postar, moderar, Meme da Semana e testes                    |
