/**
 * Comandos do bot de memes no Discord (/meme, /termometro e /ajuda) e o relógio do bot.
 *
 * Roda de graça na Cloudflare Workers. O Discord manda cada comando para o endereço do
 * Worker; ele confere a assinatura, responde na hora ("pensando...") e depois edita a
 * resposta com o meme ou o termômetro. De hora em hora, o Worker também acorda o bot no
 * GitHub Actions (o agendador do próprio GitHub atrasa horas ou nem roda).
 *
 * As fontes, a régua e os memes que já saíram vêm do painel que o bot salva no GitHub
 * (dados/painel.json). Por isso não há nada para configurar aqui: mudou o config.yml,
 * os comandos acompanham no próximo post do bot.
 */

const API = "https://discord.com/api/v10";
const MEME_API = "https://meme-api.com/gimme";
const USER_AGENT = "DiscordBot (https://github.com/vinicius-rebelatto/memes-aleatorios, 1.0)";
const USER_AGENT_MEMES = "memes-aleatorios (bot de Discord)";
const EXTENSOES = [".jpg", ".jpeg", ".png", ".gif", ".webp"];
const LIMITE_DE_UPLOAD = 10 * 1024 * 1024; // se o Discord não disser o limite do servidor
const IDS_POR_DIA = 1_450_000; // posts novos no Reddit inteiro por dia (para estimar a idade)
const MEIA_VIDA_DIAS = 3;
const IDADE_MAXIMA_DIAS = 60;
const IDADE_MAXIMA_ESCOLHIDO_DIAS = 365; // subreddit escolhido de propósito: aceita posts mais antigos
const FONTES_POR_TENTATIVA = 3;
const EFEMERA = 64; // mensagem que só quem usou o comando vê
const SEM_MENCOES = { parse: [] };
const FONTES_DE_RESERVA = ["eu_nvr", "circojeca", "MemesBR", "dankmemes", "HolUp"]; // se o painel falhar
const REACOES_PADRAO = { engracado: "😂", sem_graca: "😐", mais_pesado: "🌶️", passou_do_ponto: "🚫" };

export const TIPO = { PING: 1, COMANDO: 2, AUTOCOMPLETAR: 4 };
export const RESPOSTA = { PONG: 1, MENSAGEM: 4, PENSANDO: 5, SUGESTOES: 8 };

class ErroDeFonte extends Error {
  constructor(mensagem, status) {
    super(mensagem);
    this.status = status;
  }
}

// ---- assinatura do Discord ----------------------------------------------------------

function hexParaBytes(hex) {
  if (typeof hex !== "string" || hex.length % 2 || /[^0-9a-f]/i.test(hex)) throw new Error("hex inválido");
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(hex.slice(2 * i, 2 * i + 2), 16);
  return bytes;
}

const chaves = new Map();

async function importarChave(hex) {
  if (!chaves.has(hex)) {
    const bytes = hexParaBytes(hex);
    const promessa = crypto.subtle
      .importKey("raw", bytes, { name: "Ed25519" }, false, ["verify"])
      .catch(() =>
        crypto.subtle.importKey("raw", bytes, { name: "NODE-ED25519", namedCurve: "NODE-ED25519" }, false, [
          "verify",
        ]),
      );
    chaves.set(hex, promessa);
  }
  try {
    return await chaves.get(hex);
  } catch (erro) {
    chaves.delete(hex);
    throw erro;
  }
}

/** O Discord assina cada pedido; sem assinatura válida, o pedido não veio dele. */
export async function assinaturaValida(request, corpo, chavePublica) {
  const assinatura = request.headers.get("x-signature-ed25519");
  const horario = request.headers.get("x-signature-timestamp");
  if (!assinatura || !horario || !chavePublica) return false;
  try {
    const chave = await importarChave(chavePublica);
    const mensagem = new TextEncoder().encode(horario + corpo);
    return await crypto.subtle.verify(chave.algorithm, chave, hexParaBytes(assinatura), mensagem);
  } catch {
    return false;
  }
}

// ---- entrada ------------------------------------------------------------------------

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") {
      return new Response("🤖 Bot de memes: os comandos do Discord chegam aqui.", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    const corpo = await request.text();
    if (!(await assinaturaValida(request, corpo, env.DISCORD_PUBLIC_KEY))) {
      return new Response("assinatura inválida", { status: 401 });
    }
    let interacao;
    try {
      interacao = JSON.parse(corpo);
    } catch {
      return new Response("JSON inválido", { status: 400 });
    }
    return responder(interacao, env, ctx);
  },

  async scheduled(_evento, env, ctx) {
    ctx.waitUntil(acordarOBot(env));
  },
};

// ---- relógio: acorda o bot de hora em hora ---------------------------------------------

/** Dispara o workflow "Postar meme" no modo agenda (o bot confere se é hora de postar). */
export async function acordarOBot(env) {
  const token = String(env.RELOGIO_GITHUB_TOKEN || "").trim();
  if (!token) {
    console.log("⏰ Relógio desligado: falta o secret RELOGIO_GITHUB_TOKEN (passo 6 do README).");
    return false;
  }
  const url = `https://api.github.com/repos/${env.REPOSITORIO}/actions/workflows/postar-meme.yml/dispatches`;
  try {
    const resposta = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT_MEMES,
      },
      body: JSON.stringify({ ref: "main", inputs: { modo: "agenda" } }),
    });
    if (resposta.ok) {
      console.log("⏰ Bot acordado.");
      return true;
    }
    console.error(`⏰ O GitHub recusou (${resposta.status}): ${(await resposta.text()).slice(0, 300)}`);
  } catch (erro) {
    console.error("⏰ Não consegui falar com o GitHub:", erro.message);
  }
  return false;
}

const COMANDOS = {
  meme: { trabalho: mandarMeme, efemera: false },
  termometro: { trabalho: mostrarTermometro, efemera: false },
  ajuda: { trabalho: mostrarAjuda, efemera: true },
};

export async function responder(interacao, env, ctx) {
  if (interacao.type === TIPO.PING) return json({ type: RESPOSTA.PONG });
  if (interacao.type === TIPO.AUTOCOMPLETAR) {
    return json({ type: RESPOSTA.SUGESTOES, data: { choices: await sugerirFontes(interacao, env) } });
  }
  const comando = interacao.type === TIPO.COMANDO ? COMANDOS[interacao.data?.name] : undefined;
  if (!comando) {
    return json({ type: RESPOSTA.MENSAGEM, data: { content: "Não conheço esse comando. Tenta `/ajuda`.", flags: EFEMERA } });
  }
  // O Discord espera resposta em até 3 segundos: responde "pensando..." e termina o trabalho depois.
  ctx.waitUntil(executarComSeguranca(comando.trabalho, interacao, env));
  return json(comando.efemera ? { type: RESPOSTA.PENSANDO, data: { flags: EFEMERA } } : { type: RESPOSTA.PENSANDO });
}

async function executarComSeguranca(trabalho, interacao, env) {
  try {
    await trabalho(interacao, env);
  } catch (erro) {
    console.error(`/${interacao.data?.name} falhou:`, erro);
    await avisarProblema(interacao, "😵 Deu ruim aqui. Tenta de novo daqui a pouco.").catch(() => {});
  }
}

function json(dados) {
  return new Response(JSON.stringify(dados), { headers: { "content-type": "application/json" } });
}

// ---- respostas no Discord -----------------------------------------------------------

function urlDaResposta(interacao, sufixo = "/messages/@original") {
  return `${API}/webhooks/${interacao.application_id}/${interacao.token}${sufixo}`;
}

async function chamarDiscord(url, opcoes = {}) {
  const resposta = await fetch(url, { ...opcoes, headers: { "User-Agent": USER_AGENT, ...(opcoes.headers || {}) } });
  if (!resposta.ok) {
    throw new Error(`Discord respondeu ${resposta.status}: ${(await resposta.text()).slice(0, 300)}`);
  }
  return resposta;
}

function editarResposta(interacao, dados) {
  return chamarDiscord(urlDaResposta(interacao), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ allowed_mentions: SEM_MENCOES, ...dados }),
  });
}

/** Problema só para quem pediu: apaga o "pensando..." e manda um aviso que só a pessoa vê. */
async function avisarProblema(interacao, texto) {
  try {
    await chamarDiscord(urlDaResposta(interacao), { method: "DELETE" });
    await chamarDiscord(urlDaResposta(interacao, ""), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: texto, flags: EFEMERA, allowed_mentions: SEM_MENCOES }),
    });
  } catch {
    await editarResposta(interacao, { content: texto });
  }
}

// ---- painel (dados/painel.json no GitHub) ---------------------------------------------

export async function lerPainel(env) {
  const resposta = await fetch(env.PAINEL_URL, {
    headers: { "User-Agent": USER_AGENT_MEMES },
    cf: { cacheTtl: 60, cacheEverything: true },
    signal: AbortSignal.timeout(2500),
  });
  if (!resposta.ok) throw new Error(`o painel respondeu ${resposta.status}`);
  return resposta.json();
}

async function lerPainelOuNada(env) {
  try {
    return await lerPainel(env);
  } catch (erro) {
    console.warn("sem painel:", erro.message);
    return null;
  }
}

// ---- /meme --------------------------------------------------------------------------

function opcao(interacao, nome) {
  return interacao.data?.options?.find((item) => item.name === nome)?.value;
}

/** "r/MinecraftMemes", "/r/dankmemes/" → nome limpo; null se não parece nome de subreddit. */
export function limparSubreddit(texto) {
  const nome = String(texto ?? "")
    .trim()
    .replace(/^\/?r\//i, "")
    .replace(/\/+$/, "");
  return /^[A-Za-z0-9_]{2,21}$/.test(nome) ? nome : null;
}

/** Ordem das fontes por sorteio: quanto maior a chance, mais cedo a fonte vem (como no bot). */
export function sortearFontes(fontes, aleatorio = Math.random) {
  return fontes
    .map((fonte) => ({ fonte, chave: fonte.chance > 0 ? aleatorio() ** (1 / fonte.chance) : -1 }))
    .sort((a, b) => b.chave - a.chave)
    .map((item) => item.fonte);
}

export function idDoPost(link) {
  const achado = /(?:\/\/redd\.it\/|\/comments\/)([0-9a-z]+)/i.exec(link || "");
  return achado ? parseInt(achado[1].toLowerCase(), 36) : null;
}

export function ehImagem(url) {
  const caminho = String(url || "")
    .toLowerCase()
    .split("?")[0];
  return EXTENSOES.some((extensao) => caminho.endsWith(extensao));
}

export function nomeDoArquivo(url) {
  const caminho = String(url || "")
    .toLowerCase()
    .split("?")[0];
  const extensao = EXTENSOES.find((item) => caminho.endsWith(item)) || ".jpg";
  return "meme" + (extensao === ".jpeg" ? ".jpg" : extensao);
}

export async function buscarMemes(subreddit) {
  const resposta = await fetch(`${MEME_API}/${encodeURIComponent(subreddit)}/50`, {
    headers: { "User-Agent": USER_AGENT_MEMES },
    signal: AbortSignal.timeout(8000),
  });
  let dados = null;
  try {
    dados = await resposta.json();
  } catch {
    // resposta sem JSON: o erro sai abaixo
  }
  if (!resposta.ok || !Array.isArray(dados?.memes)) {
    throw new ErroDeFonte(dados?.message || `a meme-api respondeu ${resposta.status}`, resposta.status);
  }
  return dados.memes;
}

/**
 * Sorteia um meme: só imagens, sem spoiler, sem os que o bot mandou nos últimos dias e com
 * menos de 60 dias. Os mais votados e mais novos têm mais chance.
 */
export function escolherMeme(
  memes,
  { recentes = new Set(), permitirNsfw = false, idadeMaxima = IDADE_MAXIMA_DIAS, aleatorio = Math.random } = {},
) {
  const ids = memes.map((meme) => idDoPost(meme.postLink)).filter((id) => id !== null);
  const maisNovo = ids.length ? Math.max(...ids) : null;
  const candidatos = [];
  for (const meme of memes) {
    if (meme.spoiler || !ehImagem(meme.url) || recentes.has(meme.postLink)) continue;
    if (meme.nsfw && !permitirNsfw) continue;
    const id = idDoPost(meme.postLink);
    const idade = id !== null && maisNovo !== null ? (maisNovo - id) / IDS_POR_DIA : null;
    if (idade !== null && idade > idadeMaxima) continue;
    const peso = Math.sqrt((Number(meme.ups) || 0) + 1) * (idade === null ? 1 : 0.5 ** (idade / MEIA_VIDA_DIAS));
    candidatos.push({ meme, peso });
  }
  if (!candidatos.length) return null;
  let sorteio = aleatorio() * candidatos.reduce((soma, item) => soma + item.peso, 0);
  for (const item of candidatos) {
    sorteio -= item.peso;
    if (sorteio <= 0) return item.meme;
  }
  return candidatos[candidatos.length - 1].meme;
}

async function mandarMeme(interacao, env) {
  const pedido = String(opcao(interacao, "subreddit") ?? "").trim();
  const painel = await lerPainelOuNada(env);
  const recentes = new Set(painel?.recentes ?? []);
  const canalMais18 = interacao.channel?.nsfw === true;

  let fontes;
  if (pedido) {
    const nome = limparSubreddit(pedido);
    if (!nome) {
      return avisarProblema(interacao, "🤔 Isso não parece nome de subreddit. Escreve só o nome, tipo `MinecraftMemes`.");
    }
    const doConfig = new Set((painel?.fontes ?? []).map((fonte) => fonte.subreddit.toLowerCase()));
    fontes = [{ subreddit: nome, livre: !doConfig.has(nome.toLowerCase()) }];
  } else {
    const lista = painel?.fontes?.length ? painel.fontes : FONTES_DE_RESERVA.map((subreddit) => ({ subreddit, chance: 1 }));
    fontes = sortearFontes(lista).slice(0, FONTES_POR_TENTATIVA);
  }

  const problemas = [];
  for (const fonte of fontes) {
    let memes;
    try {
      memes = await buscarMemes(fonte.subreddit);
    } catch (erro) {
      problemas.push({ fonte, erro });
      continue;
    }
    // NSFW só sai das fontes do config.yml e só em canal restrito por idade.
    // Outro subreddit escolhido na hora nunca traz NSFW: o /meme é para memes.
    const permitirNsfw = canalMais18 && !fonte.livre;
    const idadeMaxima = pedido ? IDADE_MAXIMA_ESCOLHIDO_DIAS : IDADE_MAXIMA_DIAS;
    const meme = escolherMeme(memes, { recentes, permitirNsfw, idadeMaxima });
    if (meme) return enviarImagem(interacao, meme);
    problemas.push({ fonte, erro: null });
  }

  console.warn("sem meme:", problemas.map(({ fonte, erro }) => `r/${fonte.subreddit}: ${erro?.message ?? "nada novo"}`));
  if (!pedido) return avisarProblema(interacao, "😕 Não achei meme novo agora. Tenta de novo daqui a pouco.");
  const erro = problemas[0]?.erro;
  if (erro && [403, 404].includes(erro.status)) {
    return avisarProblema(interacao, `🤔 O r/${fontes[0].subreddit} não existe ou está fechado.`);
  }
  const regra = canalMais18 && !fontes[0].livre ? "só vale imagem" : "só vale imagem e nada NSFW";
  return avisarProblema(interacao, `😕 Não achei meme novo em r/${fontes[0].subreddit} agora (${regra}). Tenta outro subreddit.`);
}

async function baixarImagem(url, limite) {
  try {
    const resposta = await fetch(url, { headers: { "User-Agent": USER_AGENT_MEMES }, signal: AbortSignal.timeout(10000) });
    const tipo = (resposta.headers.get("content-type") || "").toLowerCase();
    if (!resposta.ok || !tipo.startsWith("image/")) return null;
    if (Number(resposta.headers.get("content-length") || 0) > limite) return null;
    const bytes = await resposta.arrayBuffer();
    return bytes.byteLength > 0 && bytes.byteLength <= limite ? { bytes, tipo } : null;
  } catch {
    return null;
  }
}

/** Só a imagem, como arquivo (sem moldura nem texto). Se não der, vai o link da imagem. */
async function enviarImagem(interacao, meme) {
  const limite = Number(interacao.attachment_size_limit) || LIMITE_DE_UPLOAD;
  const imagem = await baixarImagem(meme.url, limite);
  if (imagem) {
    const nome = nomeDoArquivo(meme.url);
    const formulario = new FormData();
    formulario.append("payload_json", JSON.stringify({ attachments: [{ id: 0, filename: nome }], allowed_mentions: SEM_MENCOES }));
    formulario.append("files[0]", new Blob([imagem.bytes], { type: imagem.tipo }), nome);
    try {
      await chamarDiscord(urlDaResposta(interacao), { method: "PATCH", body: formulario });
      return;
    } catch (erro) {
      console.warn("o upload falhou, mandando o link:", erro.message);
    }
  }
  await editarResposta(interacao, { content: meme.url });
}

async function sugerirFontes(interacao, env) {
  const focada = interacao.data?.options?.find((item) => item.focused);
  const digitado = String(focada?.value ?? "")
    .trim()
    .replace(/^\/?r\//i, "")
    .toLowerCase();
  const painel = await lerPainelOuNada(env);
  const nomes = painel?.fontes?.length ? painel.fontes.map((fonte) => fonte.subreddit) : FONTES_DE_RESERVA;
  return nomes
    .filter((nome) => nome.toLowerCase().includes(digitado))
    .slice(0, 25)
    .map((nome) => ({ name: `r/${nome}`, value: nome }));
}

// ---- /termometro e /ajuda -------------------------------------------------------------

function numeroBr(valor) {
  return Number(valor).toFixed(1).replace(".", ",");
}

function quandoFoi(iso) {
  const achado = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(iso || ""));
  return achado ? `${Number(achado[3])}h${achado[4]} de ${achado[2]}/${achado[1]}` : "";
}

export function textoDoTermometro(painel) {
  const r = { ...REACOES_PADRAO, ...(painel.reacoes || {}) };
  const linhas = ["🌡️ **Termômetro da galera**"];
  const semana = painel.regua_na_semana ? ` (${painel.regua_na_semana} na semana)` : "";
  linhas.push(`Régua: **${painel.regua_texto ?? `${numeroBr(painel.regua)}/5`}**${semana}`, "");
  linhas.push("**Chance de cada fonte no próximo meme**");
  for (const fonte of painel.fontes || []) {
    const porcento = Math.round(100 * fonte.chance);
    const chance = porcento < 1 ? "<1%" : `${porcento}%`;
    linhas.push(`\`${chance.padStart(4)}\` r/${fonte.subreddit}${fonte.nivel == null ? " 🎮" : ""}`);
  }
  linhas.push("");
  if (painel.em_alta?.length) linhas.push(`${r.engracado} Em alta: ${painel.em_alta.map((n) => `r/${n}`).join(", ")}`);
  if (painel.em_baixa?.length) linhas.push(`${r.sem_graca} Em baixa: ${painel.em_baixa.map((n) => `r/${n}`).join(", ")}`);
  const quando = quandoFoi(painel.atualizado_em);
  linhas.push(
    `-# 🎮 = fora da régua · ${r.mais_pesado} sobe a régua, ${r.passou_do_ponto} desce${quando ? ` · atualizado às ${quando}` : ""}`,
  );
  return linhas.join("\n");
}

export function textoDeAjuda(painel) {
  const r = { ...REACOES_PADRAO, ...(painel?.reacoes || {}) };
  const horarios = painel?.horarios;
  const quando = !horarios ? "" : horarios.startsWith("de ") ? ` ${horarios}` : ` às ${horarios}`;
  const votos = painel?.votos_para_remover ?? 3;
  const ranking = painel?.ranking ?? "domingo às 21h";
  return [
    `🤖 **Bot de memes**: manda meme no canal${quando}.`,
    "",
    "**Reaja nos memes, é assim que a galera treina o bot:**",
    `${r.engracado} engraçado: vale voto no Meme da Semana e a fonte aparece mais`,
    `${r.sem_graca} sem graça: a fonte aparece menos`,
    `${r.mais_pesado} mais pesado: sobe a régua de peso`,
    `${r.passou_do_ponto} passou do ponto: desce a régua (com ${votos} votos o meme some)`,
    "",
    "**Comandos**",
    "`/meme`: um meme agora (dá para escolher o subreddit)",
    "`/termometro`: a régua e as fontes favoritas da galera",
    "`/ajuda`: esta explicação",
    "",
    `🏆 O Meme da Semana sai ${ranking}: ganha o meme com mais ${r.engracado}.`,
  ].join("\n");
}

async function mostrarTermometro(interacao, env) {
  const painel = await lerPainelOuNada(env);
  if (!painel) return avisarProblema(interacao, "😕 Não consegui ler o termômetro agora. Tenta de novo daqui a pouco.");
  await editarResposta(interacao, { content: textoDoTermometro(painel) });
}

async function mostrarAjuda(interacao, env) {
  await editarResposta(interacao, { content: textoDeAjuda(await lerPainelOuNada(env)) });
}
