// Testes do Worker: rodam com `node --test` (sem instalar nada) e sem internet.
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import worker, {
  RESPOSTA,
  TIPO,
  acordarOBot,
  escolherMeme,
  idDoPost,
  limparSubreddit,
  nomeDoArquivo,
  responder,
  sortearFontes,
  textoDeAjuda,
  textoDoTermometro,
} from "../src/index.js";
import { limparToken } from "../registrar.mjs";

const PAINEL_URL = "https://raw.githubusercontent.com/exemplo/painel.json";
const PAINEL = {
  atualizado_em: "2026-11-22T22:06:44-03:00",
  regua: 5,
  regua_texto: "5,0/5 🟩🟩🟨🟧🟥",
  regua_na_semana: "🌶️ subiu 2,0",
  horarios: "de hora em hora, das 9h às 2h",
  ranking: "domingo às 21h",
  votos_para_remover: 3,
  reacoes: { engracado: "😂", sem_graca: "😐", mais_pesado: "🌶️", passou_do_ponto: "🚫" },
  fontes: [
    { subreddit: "circojeca", nivel: 5, chance: 0.6, afinidade: 0.5 },
    { subreddit: "MinecraftMemes", nivel: null, chance: 0.396, afinidade: 0 },
    { subreddit: "MemesBR", nivel: 2, chance: 0.004, afinidade: 0 },
  ],
  em_alta: ["circojeca"],
  em_baixa: ["HUEstation"],
  recentes: ["https://redd.it/1y00001"],
};

function memeDaApi(id, { ups = 100, nsfw = false, spoiler = false, url } = {}) {
  return { postLink: `https://redd.it/${id}`, url: url ?? `https://i.redd.it/${id}.png`, ups, nsfw, spoiler };
}

/** Imita a internet: cada chamada de fetch passa por aqui e fica registrada. */
function internetFalsa({ painel = PAINEL, memes = {}, imagem = true, falhas = {} } = {}) {
  const chamadas = [];
  const fetchFalso = async (url, opcoes = {}) => {
    const metodo = opcoes.method || "GET";
    chamadas.push({ url: String(url), metodo, opcoes });
    if (url === PAINEL_URL) {
      return painel ? Response.json(painel) : new Response("sumiu", { status: 404 });
    }
    const daApi = /meme-api\.com\/gimme\/([^/]+)\/50$/.exec(url);
    if (daApi) {
      const nome = decodeURIComponent(daApi[1]);
      if (falhas[nome]) return Response.json({ code: falhas[nome], message: "This subreddit does not exist." }, { status: falhas[nome] });
      return Response.json({ count: (memes[nome] || []).length, memes: memes[nome] || [] });
    }
    if (String(url).startsWith("https://i.redd.it/")) {
      return imagem ? new Response(new Uint8Array([137, 80, 78, 71]), { headers: { "content-type": "image/png" } }) : new Response("x", { status: 403 });
    }
    if (String(url).startsWith("https://discord.com/api/v10/webhooks/")) {
      return metodo === "DELETE" ? new Response(null, { status: 204 }) : Response.json({ id: "1" });
    }
    throw new Error(`fetch inesperado: ${metodo} ${url}`);
  };
  return { chamadas, fetchFalso };
}

function contexto() {
  const tarefas = [];
  return { tarefas, waitUntil: (promessa) => tarefas.push(promessa) };
}

function comando(nome, opcoes = [], extra = {}) {
  return { type: TIPO.COMANDO, application_id: "123", token: "tok", data: { name: nome, options: opcoes }, ...extra };
}

async function rodar(interacao, internet) {
  globalThis.fetch = internet.fetchFalso;
  const ctx = contexto();
  const resposta = await responder(interacao, { PAINEL_URL }, ctx);
  await Promise.all(ctx.tarefas);
  return { resposta: await resposta.json(), discord: internet.chamadas.filter((c) => c.url.includes("discord.com")) };
}

const fetchOriginal = globalThis.fetch;
const randomOriginal = Math.random;
beforeEach(() => {
  Math.random = () => 0.5;
});
afterEach(() => {
  globalThis.fetch = fetchOriginal;
  Math.random = randomOriginal;
});

// ---- assinatura -------------------------------------------------------------------------

describe("assinatura do Discord", () => {
  async function chaves() {
    const par = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
    const publica = Buffer.from(await crypto.subtle.exportKey("raw", par.publicKey)).toString("hex");
    return { par, publica };
  }

  async function pedido(par, corpo, horario = "1700000000") {
    const assinatura = await crypto.subtle.sign("Ed25519", par.privateKey, new TextEncoder().encode(horario + corpo));
    return new Request("https://worker.exemplo/", {
      method: "POST",
      body: corpo,
      headers: { "x-signature-ed25519": Buffer.from(assinatura).toString("hex"), "x-signature-timestamp": horario },
    });
  }

  it("responde PONG ao PING assinado", async () => {
    const { par, publica } = await chaves();
    const resposta = await worker.fetch(await pedido(par, JSON.stringify({ type: 1 })), { DISCORD_PUBLIC_KEY: publica }, contexto());
    assert.equal(resposta.status, 200);
    assert.deepEqual(await resposta.json(), { type: RESPOSTA.PONG });
  });

  it("recusa assinatura errada, de outra chave ou ausente", async () => {
    const { par, publica } = await chaves();
    const outra = await chaves();
    const env = { DISCORD_PUBLIC_KEY: publica };
    const adulterado = await pedido(par, JSON.stringify({ type: 1 }));
    const corpoTrocado = new Request(adulterado.url, { method: "POST", body: '{"type":2}', headers: adulterado.headers });
    assert.equal((await worker.fetch(corpoTrocado, env, contexto())).status, 401);
    assert.equal((await worker.fetch(await pedido(outra.par, '{"type":1}'), env, contexto())).status, 401);
    const semAssinatura = new Request("https://worker.exemplo/", { method: "POST", body: '{"type":1}' });
    assert.equal((await worker.fetch(semAssinatura, env, contexto())).status, 401);
  });

  it("GET mostra que o Worker está no ar", async () => {
    const resposta = await worker.fetch(new Request("https://worker.exemplo/"), {}, contexto());
    assert.equal(resposta.status, 200);
    assert.match(await resposta.text(), /Bot de memes/);
  });
});

// ---- /meme ------------------------------------------------------------------------------

describe("/meme", () => {
  it("responde 'pensando' e depois edita com só a imagem, como arquivo", async () => {
    const internet = internetFalsa({ memes: { circojeca: [memeDaApi("1y00002", { ups: 50 })] } });
    const { resposta, discord } = await rodar(comando("meme"), internet);
    assert.deepEqual(resposta, { type: RESPOSTA.PENSANDO });
    assert.equal(discord.length, 1);
    assert.equal(discord[0].metodo, "PATCH");
    assert.equal(discord[0].url, "https://discord.com/api/v10/webhooks/123/tok/messages/@original");
    const formulario = discord[0].opcoes.body;
    assert.ok(formulario instanceof FormData);
    assert.deepEqual(JSON.parse(formulario.get("payload_json")), {
      attachments: [{ id: 0, filename: "meme.png" }],
      allowed_mentions: { parse: [] },
    });
    assert.equal(formulario.get("files[0]").name, "meme.png");
  });

  it("sem conseguir baixar a imagem, manda o link dela", async () => {
    const internet = internetFalsa({ memes: { circojeca: [memeDaApi("1y00002")] }, imagem: false });
    const { discord } = await rodar(comando("meme"), internet);
    assert.deepEqual(JSON.parse(discord[0].opcoes.body), {
      allowed_mentions: { parse: [] },
      content: "https://i.redd.it/1y00002.png",
    });
  });

  it("pula o que o bot já mandou e tenta a próxima fonte", async () => {
    const internet = internetFalsa({
      memes: { circojeca: [memeDaApi("1y00001")], MinecraftMemes: [memeDaApi("1y00003")] },
    });
    const { discord } = await rodar(comando("meme"), internet);
    const pedidos = internet.chamadas.filter((c) => c.url.includes("meme-api")).map((c) => c.url.split("/")[4]);
    assert.deepEqual(pedidos, ["circojeca", "MinecraftMemes"]);
    assert.equal(discord[0].opcoes.body.get("files[0]").name, "meme.png");
  });

  it("subreddit escolhido: aceita 'r/' e nunca traz NSFW, nem em canal +18", async () => {
    const internet = internetFalsa({ memes: { qualquercoisa: [memeDaApi("1y00002", { nsfw: true })] } });
    const interacao = comando("meme", [{ name: "subreddit", value: "r/qualquercoisa" }], { channel: { nsfw: true } });
    const { discord } = await rodar(interacao, internet);
    assert.deepEqual(
      discord.map((c) => c.metodo),
      ["DELETE", "POST"],
    ); // apaga o "pensando" e avisa só quem pediu
    const aviso = JSON.parse(discord[1].opcoes.body);
    assert.equal(aviso.flags, 64);
    assert.match(aviso.content, /Não achei meme em r\/qualquercoisa/);
  });

  it("fonte do config.yml pode trazer NSFW, mas só em canal +18", async () => {
    const memes = { circojeca: [memeDaApi("1y00002", { nsfw: true })] };
    const pedido = [{ name: "subreddit", value: "circojeca" }];
    let { discord } = await rodar(comando("meme", pedido, { channel: { nsfw: true } }), internetFalsa({ memes }));
    assert.equal(discord[0].metodo, "PATCH");
    ({ discord } = await rodar(comando("meme", pedido, { channel: { nsfw: false } }), internetFalsa({ memes })));
    assert.deepEqual(
      discord.map((c) => c.metodo),
      ["DELETE", "POST"],
    );
  });

  it("subreddit que não existe ou nome inválido viram aviso só para quem pediu", async () => {
    const internet = internetFalsa({ falhas: { naoexiste123: 404 } });
    let { discord } = await rodar(comando("meme", [{ name: "subreddit", value: "naoexiste123" }]), internet);
    assert.match(JSON.parse(discord[1].opcoes.body).content, /não existe ou está fechado/);
    ({ discord } = await rodar(comando("meme", [{ name: "subreddit", value: "isso não é nome" }]), internetFalsa()));
    assert.match(JSON.parse(discord[1].opcoes.body).content, /não parece nome de subreddit/);
  });

  it("sem painel, usa as fontes de reserva", async () => {
    const internet = internetFalsa({ painel: null, memes: { eu_nvr: [memeDaApi("1y00002")], circojeca: [], MemesBR: [], dankmemes: [], HolUp: [] } });
    const { discord } = await rodar(comando("meme"), internet);
    assert.equal(discord.at(-1).metodo, "PATCH");
  });

  it("autocompletar sugere as fontes do config.yml", async () => {
    globalThis.fetch = internetFalsa().fetchFalso;
    const interacao = { type: TIPO.AUTOCOMPLETAR, data: { name: "meme", options: [{ name: "subreddit", value: "r/mine", focused: true }] } };
    const resposta = await (await responder(interacao, { PAINEL_URL }, contexto())).json();
    assert.deepEqual(resposta, { type: RESPOSTA.SUGESTOES, data: { choices: [{ name: "r/MinecraftMemes", value: "MinecraftMemes" }] } });
  });
});

describe("escolha do meme", () => {
  it("só imagem, sem spoiler, sem repetido, sem NSFW e sem meme velho", () => {
    const memes = [
      memeDaApi("1y00010"),
      memeDaApi("1y00011", { spoiler: true }),
      memeDaApi("1y00012", { url: "https://v.redd.it/video" }),
      memeDaApi("1y00013", { nsfw: true }),
      memeDaApi("1x00000"), // ~1 mês e meio antes dos outros... ainda vale
      memeDaApi("1t00000"), // meses antes: velho demais
    ];
    const recentes = new Set(["https://redd.it/1y00010"]);
    const sorteados = new Set();
    for (const valor of [0, 0.3, 0.6, 0.99]) {
      sorteados.add(escolherMeme(memes, { recentes, aleatorio: () => valor })?.postLink);
    }
    assert.deepEqual([...sorteados].sort(), ["https://redd.it/1x00000"]);
    assert.equal(escolherMeme(memes, { recentes, permitirNsfw: true, aleatorio: () => 0 }).postLink, "https://redd.it/1y00013");
    assert.equal(escolherMeme([memeDaApi("1y1", { spoiler: true })]), null);
  });

  it("ajudantes", () => {
    assert.equal(limparSubreddit(" /r/MinecraftMemes/ "), "MinecraftMemes");
    assert.equal(limparSubreddit("a"), null);
    assert.equal(limparSubreddit("dois nomes"), null);
    assert.equal(idDoPost("https://www.reddit.com/r/memes/comments/1y2s9db/titulo/"), parseInt("1y2s9db", 36));
    assert.equal(idDoPost("https://i.redd.it/abc.png"), null);
    assert.equal(nomeDoArquivo("https://i.redd.it/x.JPEG?width=1"), "meme.jpg");
    assert.equal(nomeDoArquivo("https://i.redd.it/x.gif"), "meme.gif");
    const ordem = sortearFontes(
      [
        { subreddit: "zero", chance: 0 },
        { subreddit: "pouca", chance: 0.1 },
        { subreddit: "muita", chance: 0.9 },
      ],
      () => 0.5,
    );
    assert.deepEqual(
      ordem.map((f) => f.subreddit),
      ["muita", "pouca", "zero"],
    );
  });
});

// ---- /termometro e /ajuda -----------------------------------------------------------------

describe("/termometro e /ajuda", () => {
  it("/termometro mostra régua, chances e quem está em alta, para todo mundo", async () => {
    const { resposta, discord } = await rodar(comando("termometro"), internetFalsa());
    assert.deepEqual(resposta, { type: RESPOSTA.PENSANDO });
    const texto = JSON.parse(discord[0].opcoes.body).content;
    assert.equal(texto, textoDoTermometro(PAINEL));
    assert.deepEqual(texto.split("\n"), [
      "🌡️ **Termômetro da galera**",
      "Régua: **5,0/5 🟩🟩🟨🟧🟥** (🌶️ subiu 2,0 na semana)",
      "",
      "**Chance de cada fonte no próximo meme**",
      "` 60%` r/circojeca",
      "` 40%` r/MinecraftMemes 🎮",
      "` <1%` r/MemesBR",
      "",
      "😂 Em alta: r/circojeca",
      "😐 Em baixa: r/HUEstation",
      "-# 🎮 = fora da régua · 🌶️ sobe a régua, 🚫 desce · atualizado às 22h06 de 22/11",
    ]);
  });

  it("/termometro sem painel avisa só quem pediu", async () => {
    const { discord } = await rodar(comando("termometro"), internetFalsa({ painel: null }));
    assert.deepEqual(
      discord.map((c) => c.metodo),
      ["DELETE", "POST"],
    );
  });

  it("/ajuda explica as reações e só quem pediu vê", async () => {
    const { resposta, discord } = await rodar(comando("ajuda"), internetFalsa());
    assert.deepEqual(resposta, { type: RESPOSTA.PENSANDO, data: { flags: 64 } });
    const texto = JSON.parse(discord[0].opcoes.body).content;
    assert.match(texto, /manda meme no canal de hora em hora, das 9h às 2h\./);
    assert.match(texto, /🚫 passou do ponto: desce a régua \(com 3 votos o meme some\)/);
    assert.match(texto, /Meme da Semana sai domingo às 21h/);
    assert.match(textoDeAjuda(null), /manda meme no canal\./);
  });

  it("comando desconhecido", async () => {
    const { resposta } = await rodar(comando("dancinha"), internetFalsa());
    assert.equal(resposta.type, RESPOSTA.MENSAGEM);
    assert.equal(resposta.data.flags, 64);
  });
});

describe("relógio", () => {
  it("de hora em hora, dispara o Postar meme no modo agenda", async () => {
    const chamadas = [];
    globalThis.fetch = async (url, opcoes) => {
      chamadas.push({ url, opcoes });
      return new Response(null, { status: 204 });
    };
    const ctx = contexto();
    await worker.scheduled({}, { RELOGIO_GITHUB_TOKEN: " ghp_teste ", REPOSITORIO: "dono/repo" }, ctx);
    assert.deepEqual(await Promise.all(ctx.tarefas), [true]);
    assert.equal(chamadas[0].url, "https://api.github.com/repos/dono/repo/actions/workflows/postar-meme.yml/dispatches");
    assert.equal(chamadas[0].opcoes.method, "POST");
    assert.equal(chamadas[0].opcoes.headers.Authorization, "Bearer ghp_teste");
    assert.ok(chamadas[0].opcoes.headers["User-Agent"]);
    assert.deepEqual(JSON.parse(chamadas[0].opcoes.body), { ref: "main", inputs: { modo: "agenda" } });
  });

  it("sem token não faz nada; token recusado ou sem rede não derruba o Worker", async () => {
    globalThis.fetch = async () => assert.fail("não devia chamar o GitHub");
    assert.equal(await acordarOBot({ REPOSITORIO: "dono/repo" }), false);
    globalThis.fetch = async () => new Response('{"message":"Bad credentials"}', { status: 401 });
    assert.equal(await acordarOBot({ RELOGIO_GITHUB_TOKEN: "x", REPOSITORIO: "dono/repo" }), false);
    globalThis.fetch = async () => {
      throw new TypeError("fetch failed");
    };
    assert.equal(await acordarOBot({ RELOGIO_GITHUB_TOKEN: "x", REPOSITORIO: "dono/repo" }), false);
  });
});

describe("registrar", () => {
  it("limpa o token como o bot", () => {
    assert.equal(limparToken(' "Bot abc.def" '), "abc.def");
    assert.equal(limparToken("abc"), "abc");
    assert.equal(limparToken(undefined), "");
  });
});
