# 🤖 Memes Aleatórios

Automação que posta memes no canal `#memes-aleatorios` do nosso Discord (brasileiros, de humor mais pesado e de
jogos), com votação, **Meme da Semana**, comandos (`/meme`, `/termometro`, `/ajuda`) e um **algoritmo da galera**:
as reações de todo mundo decidem que tipo de meme vem depois. Roda de graça no GitHub Actions e na Cloudflare:
não tem servidor, nem nada ligado o tempo todo.

## Como funciona

**18 memes por dia, de hora em hora, das 9h às 2h da manhã** (horário de Brasília). O meme chega **só a imagem**,
sem moldura, título ou texto, com 4 reações:

| Reação | Significa         | O que muda                                                     |
| ------ | ----------------- | -------------------------------------------------------------- |
| 😂     | achei engraçado   | memes daquela fonte aparecem mais (e vale voto no Meme da Semana) |
| 😐     | sem graça         | memes daquela fonte aparecem menos                             |
| 🌶️     | quero mais pesado | a régua sobe                                                   |
| 🚫     | passou do ponto   | a régua desce, e com **3 pessoas** marcando o bot apaga o meme |

- **Domingo às 21h** sai o 🏆 **Meme da Semana** com o pódio e o 🌡️ termômetro da galera. Memes que a galera
  posta no canal também concorrem.
- O bot **acorda de hora em hora**: confere os 🚫, apaga o que passou do ponto e, se for um dos horários, posta.
  Ele mesmo confere a hora, então **nunca posta entre 2h e 9h nem posta dois memes no mesmo horário**, mesmo que
  seja acordado atrasado ou mais de uma vez.
- De vez em quando (20%) ele posta do [estoque da galera](#-estoque-da-galera).
- Comandos: `/meme` manda um meme na hora, `/termometro` mostra a régua e `/ajuda` explica as reações
  (veja o [passo 7](#7-comandos-meme-termometro-e-ajuda)).

> 💡 Sugestão de tópico para o canal (Editar canal → Tópico): *Meme de hora em hora 🤖 Reaja: 😂 engraçado ·
> 😐 sem graça · 🌶️ mais pesado · 🚫 passou do ponto (3 🚫 apagam). /meme pede um na hora, /termometro mostra a régua.*

### 🌡️ O algoritmo da galera

Cada fonte de memes (um subreddit) tem um **nível de peso**, de 1 (leve) a 5 (pesado):

| Nível          | Fontes                                                      |
| -------------- | ----------------------------------------------------------- |
| 2              | r/DiretoDoZapZap, r/MemesBR                                 |
| 3              | r/HUEstation                                                |
| 4              | r/eu_nvr, r/dankmemes                                       |
| 5              | r/circojeca, r/HolUp                                        |
| 🎮 fora da régua | r/leagueofmemes, r/MinecraftMemes, r/dontstarve (jogos)    |

- A **régua** sobe um pouco a cada 🌶️ e desce a cada 🚫.
- Na hora de escolher, o bot prefere as fontes com nível **perto da régua** e com mais 😂 do que 😐.
- As fontes de **jogos ficam fora da régua**: saem sempre na mesma proporção (cerca de 1 em cada 4 memes),
  mas os 😂 e 😐 também valem para elas.
- Dentro da fonte, ele pega o meme **mais votado entre os recentes**: post velho não ganha de post do momento.
- **1 em cada 5 posts é surpresa**: ignora a régua (mas não os 😂 e 😐) e sorteia a fonte, para o algoritmo
  não ficar viciado e perceber quando o gosto da galera muda.
- A régua não aparece nos memes: quem quiser ver usa `/termometro`, e ela sai também no anúncio de domingo.

O estado do algoritmo fica em `dados/termometro.json` e o que já foi postado em `dados/historico.json`
(é por isso que meme não repete). O bot atualiza os dois sozinho.

### 🔞 NSFW

Memes marcados como NSFW no Reddit podem sair, contando como **um nível mais pesado** na régua: quanto mais
alta a régua, mais chance de aparecer. Mas o Discord só permite conteúdo adulto em canal marcado como
restrito por idade, então o bot **só posta NSFW se o canal estiver marcado assim**. Para ligar:
**Editar canal → Visão geral → Canal com restrição de idade**. Quem abrir o canal vai precisar confirmar que
tem 18 anos ou mais. Sem essa marcação, o bot simplesmente deixa os NSFW de fora.

No `/meme` vale a mesma regra, com um detalhe: NSFW só vem das fontes do `config.yml`. Um subreddit escolhido na
hora (`/meme subreddit:...`) nunca traz post NSFW, nem em canal restrito.

## Instalação (uma vez só)

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
https://discord.com/oauth2/authorize?client_id=SEU_APPLICATION_ID&scope=bot+applications.commands&permissions=117824
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

Aba **Actions → Postar meme → Run workflow**, deixe o modo em **agora** e clique em **Run workflow**.
Em um minuto o meme aparece no canal. ✅

Os outros modos do botão: **agenda** (só posta se for horário), **ranking** (anuncia o Meme da Semana na hora)
e **simular** (testa todas as fontes e mostra no log qual meme seria postado, sem postar nada).

### 6. Relógio externo para os horários certinhos (recomendado)

O agendador do próprio GitHub anda atrasando execuções em **horas** e às vezes nem roda. O bot já se protege
disso (nunca posta fora de hora), mas para os memes saírem **na hora certa** vale colocar um relógio externo
gratuito, o [cron-job.org](https://cron-job.org), para acordar o bot de hora em hora. Leva uns 5 minutos.

**a) Criar um token só para acordar o bot.** No GitHub: sua foto → **Settings → Developer settings →
Personal access tokens → Fine-grained tokens → Generate new token**.

- **Token name:** `relogio-memes`
- **Expiration:** 1 ano (anote para renovar)
- **Repository access:** *Only select repositories* → `memes-aleatorios`
- **Permissions → Repository permissions → Actions:** *Read and write* (só essa)

Gere e copie o token. Ele só consegue disparar os workflows deste repositório e mais nada.

**b) Criar o relógio no cron-job.org.** Crie uma conta grátis e clique em **Create cronjob**:

- **URL:** `https://api.github.com/repos/vinicius-rebelatto/memes-aleatorios/actions/workflows/postar-meme.yml/dispatches`
- **Execution schedule:** a cada hora, no minuto 0 (fuso `America/Sao_Paulo`)
- Na aba **Advanced**:
  - **Request method:** `POST`
  - **Headers:**
    - `Accept`: `application/vnd.github+json`
    - `Authorization`: `Bearer COLE_O_TOKEN_AQUI`
    - `Content-Type`: `application/json`
  - **Request body:** `{"ref":"main","inputs":{"modo":"agenda"}}`

Salve e use **Test run**: a resposta deve ser `204` e uma execução nova aparece na aba **Actions**. Pronto:
o bot passa a acordar pontualmente. O agendamento do GitHub continua lá como reserva.

### 7. Comandos `/meme`, `/termometro` e `/ajuda`

| Comando                         | O que faz                                                                           |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| `/meme`                         | Manda um meme na hora, sorteado pelo algoritmo da galera (só a imagem)              |
| `/meme subreddit:MinecraftMemes` | Manda um meme de um subreddit escolhido (as fontes do `config.yml` aparecem como sugestão) |
| `/termometro`                   | Mostra a régua, a chance de cada fonte e quem está em alta e em baixa              |
| `/ajuda`                        | Explica as reações e os comandos (só quem pediu vê)                                 |

Os memes do `/meme` são extras: não mexem no termômetro e não concorrem ao Meme da Semana.

Os comandos rodam num **Worker da Cloudflare**, de graça (o plano grátis aguenta 100 mil comandos por dia).
Quem publica o Worker, liga ele ao Discord e registra os comandos é o GitHub Actions; você só cria a conta e
cola dois secrets. Leva uns 10 minutos.

**a) Conta.** Crie uma conta grátis em <https://dash.cloudflare.com/sign-up> e confirme o e-mail.

**b) Endereço workers.dev.** No painel da Cloudflare, abra **Workers & Pages** (menu da esquerda) uma vez.
Isso cria o seu endereço `*.workers.dev`. Não precisa criar nenhum Worker lá.

**c) Account ID.** Ainda em **Workers & Pages**, copie o **Account ID** que aparece na lateral (ou, na página
inicial da conta, menu **⋯** ao lado do nome da conta → **Copy account ID**).

**d) Token.** Clique na sua foto (canto superior direito) → **Profile → API Tokens → Create Token**, e no modelo
**Edit Cloudflare Workers** clique em **Use template**. Em *Account Resources* escolha a sua conta e deixe
*Zone Resources* como está. **Continue to summary → Create Token** e copie o token (ele só aparece uma vez).

**e) Secrets.** No GitHub, no mesmo lugar do passo 4, crie mais dois:

| Name                    | Secret                     |
| ----------------------- | -------------------------- |
| `CLOUDFLARE_API_TOKEN`  | o token do item d          |
| `CLOUDFLARE_ACCOUNT_ID` | o Account ID do item c     |

**f) Ligar.** Aba **Actions → Comandos do Discord → Run workflow**. Em um ou dois minutos o log termina com
`✅ Comandos registrados: /meme, /termometro, /ajuda`. Digite `/` no Discord para ver os comandos (se não
aparecerem, aperte `Ctrl+R` para recarregar o Discord).

> O workflow também preenche sozinho o campo **Interactions Endpoint URL** do app no portal do Discord. Não
> precisa mexer lá. Sempre que a pasta `worker/` mudar, ele publica de novo sozinho.

## Personalizar

| Quero mudar...                              | Onde                                                  |
| ------------------------------------------- | ----------------------------------------------------- |
| Horários dos memes                          | `config.yml` → `agenda.horarios`                      |
| Dia e hora do Meme da Semana                | `config.yml` → `ranking.dia` e `ranking.horario`      |
| Fontes, o nível de cada uma e o peso        | `config.yml` → `fontes` (sem `nivel` = fora da régua) |
| Os emojis das 4 reações                     | `config.yml` → `reacoes`                              |
| Onde a régua começa e a chance de surpresa  | `config.yml` → `termometro`                           |
| Liberar ou bloquear NSFW                    | `config.yml` → `nsfw.permitir`                        |
| Quantos 🚫 apagam um meme                   | `config.yml` → `moderacao.votos_para_remover`         |
| Chance de postar do estoque                 | `config.yml` → `estoque.chance`                       |

Dá para editar direto pelo site do GitHub (ícone de lápis no arquivo → **Commit changes**). Como o bot
acorda de hora em hora, os horários podem ser qualquer hora cheia ou quebrada (ex.: `"19:30"`); o bot posta
na primeira acordada dentro da janela de cada horário.

**Quer memes mais pesados ou mais leves do que a lista permite?** A régua só vai até as fontes da lista:
adicione fontes novas com o nível certo em `config.yml` e rode o **Postar meme** no modo **simular**. O log
mostra se cada fonte funciona, quantos memes novos ela tem e os títulos dos que ela mandaria agora. Mais
jogos? Adicione o subreddit sem `nivel` e com `peso: 0.5`, como os outros jogos. Os comandos acompanham o
`config.yml` sozinhos, a partir do próximo post do bot.

## 📦 Estoque da galera

A pasta [`estoque/`](estoque/) guarda memes que a própria galera sobe. Para subir: abra a pasta →
**Add file → Upload files** → arraste as imagens → **Commit changes**.

- Formatos: `.jpg`, `.jpeg`, `.png`, `.gif` ou `.webp`, até 10 MB.
- Cada arquivo sai uma vez só.
- Para alguém conseguir subir, adicione a pessoa em **Settings → Collaborators → Add people**.

## Problemas comuns

O resultado de cada execução aparece na aba **Actions** (clique na execução para ver o resumo).

| Mensagem                                         | O que fazer                                                                                     |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| ⏰ Fora do horário de posts / ✅ O meme das 12h já saiu | Normal: o bot acordou, moderou e não era hora de postar.                                  |
| ⚠️ Não achei nenhum meme novo... Tento de novo no próximo horário | Normal de vez em quando (são 18 posts por dia). Se virar rotina, adicione fontes ou memes no estoque. |
| ⚠️ secrets ainda não foram configurados          | Faça o passo 4.                                                                                 |
| ❌ O token foi recusado                          | Gere outro token (passo 1) e atualize o secret `DISCORD_TOKEN`.                                 |
| ❌ O bot não consegue ver o canal / Falta permissão | Convide de novo com o link do passo 2. Se o canal ou a categoria for restrito, libere o cargo do bot nele. |
| ❌ Canal não encontrado                          | O `DISCORD_CHANNEL_ID` está errado: copie o ID de novo (passo 3).                               |
| ❌ Não achei nenhum meme novo                    | A meme-api pode estar fora do ar. Se continuar, adicione outra fonte ou memes no estoque.       |
| ℹ️ NSFW fica de fora                             | Normal: o canal não está marcado como restrito por idade (veja [NSFW](#-nsfw)).                 |
| cron-job.org mostra erro `401`, `403` ou `404`   | Token errado, sem a permissão *Actions: Read and write*, vencido, ou URL digitada errada.        |
| ⚠️ Os comandos ainda não foram ligados          | Faça o [passo 7](#7-comandos-meme-termometro-e-ajuda).                                          |
| Comandos não aparecem no Discord                 | Aperte `Ctrl+R` no Discord e confira se o **Comandos do Discord** terminou com ✅. Se ainda não aparecerem, convide o bot de novo com o link do passo 2. |
| "O aplicativo não respondeu" ao usar um comando  | Rode **Actions → Comandos do Discord → Run workflow** de novo: ele religa o Worker ao Discord.   |
| Comandos do Discord falha com `workers.dev`      | Faltou o item b do passo 7 (abrir **Workers & Pages** uma vez).                                 |
| Comandos do Discord falha com `Authentication error` | O token da Cloudflare está errado ou sem permissão: refaça o item d do passo 7.           |

Também é normal:

- **O bot aparece offline** na lista de membros. Ele só "acorda" para postar.
- **Commits "🤖 Bot de memes"** no histórico do repositório. É o bot salvando o que já postou e o termômetro.

## Rodar no computador (opcional)

```bash
pip install -r requirements-dev.txt
python -m bot.postar --modo simular   # testa as fontes e mostra o próximo meme, sem mexer no Discord
python -m pytest                      # roda os testes
cd worker && node --test              # testes dos comandos (precisa do Node 22 ou mais novo)
```

## Como o código está organizado

| Arquivo                | O que faz                                                                    |
| ---------------------- | ---------------------------------------------------------------------------- |
| `bot/postar.py`        | O bot: lê as reações, modera, posta se for hora e anuncia o Meme da Semana   |
| `bot/agenda.py`        | Os horários: janela de cada post e dia do Meme da Semana                     |
| `bot/termometro.py`    | O algoritmo da galera: régua de peso e afinidade de cada fonte               |
| `bot/fontes.py`        | Busca memes na [meme-api](https://github.com/D3vd/Meme_Api) e no estoque e escolhe o melhor |
| `bot/moderar.py`       | Apaga os memes do bot que levaram 🚫 suficientes                             |
| `bot/ranking.py`       | Conta os 😂 da semana e monta o anúncio com o termômetro                     |
| `bot/painel.py`        | Grava `dados/painel.json`, o resumo do termômetro que os comandos leem       |
| `bot/historico.py`     | Lê e grava `dados/historico.json`                                            |
| `bot/discord_api.py`   | Conversa com a API do Discord                                                |
| `bot/config.py`        | Lê o `config.yml` e os secrets                                               |
| `worker/`              | Os comandos do Discord (Worker da Cloudflare): `src/index.js` atende os comandos, `comandos.json` os define e `registrar.mjs` liga tudo ao Discord |
| `.github/workflows/`   | `postar-meme.yml` (o bot, de hora em hora), `comandos.yml` (publica os comandos) e `testes.yml` |
