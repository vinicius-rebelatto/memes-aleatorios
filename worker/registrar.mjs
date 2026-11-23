// Liga o Worker da Cloudflare ao Discord e registra os comandos /meme, /termometro e /ajuda.
// Roda no GitHub Actions logo depois de publicar o Worker (workflow "Comandos do Discord").
//
// Variáveis: DISCORD_TOKEN (secret do bot) e WORKER_URL (endereço que a Cloudflare deu).
// Sem WORKER_URL, monta o endereço com CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID.

import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const API = "https://discord.com/api/v10";
const USER_AGENT = "DiscordBot (https://github.com/vinicius-rebelatto/memes-aleatorios, 1.0)";
const TENTATIVAS = 6;
const ESPERA_MS = 15_000;

export function limparToken(valor) {
  let token = String(valor ?? "")
    .trim()
    .replace(/^["']|["']$/g, "")
    .trim();
  if (token.toLowerCase().startsWith("bot ")) token = token.slice(4).trim();
  return token;
}

async function discord(token, metodo, rota, corpo) {
  const resposta = await fetch(API + rota, {
    method: metodo,
    headers: { Authorization: `Bot ${token}`, "User-Agent": USER_AGENT, "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await resposta.text();
  if (!resposta.ok) {
    const erro = new Error(`o Discord respondeu ${resposta.status} em ${metodo} ${rota}: ${texto.slice(0, 500)}`);
    erro.status = resposta.status;
    throw erro;
  }
  return texto ? JSON.parse(texto) : null;
}

async function enderecoDoWorker() {
  const informado = (process.env.WORKER_URL || "").trim().replace(/\/+$/, "");
  if (informado) return informado;
  // Plano B: o endereço é https://<nome do worker>.<subdomínio da conta>.workers.dev
  const toml = await readFile(new URL("./wrangler.toml", import.meta.url), "utf8");
  const nome = /^name\s*=\s*"([^"]+)"/m.exec(toml)?.[1];
  const resposta = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${process.env.CLOUDFLARE_ACCOUNT_ID}/workers/subdomain`,
    { headers: { Authorization: `Bearer ${process.env.CLOUDFLARE_API_TOKEN}` } },
  );
  const subdominio = (await resposta.json().catch(() => null))?.result?.subdomain;
  if (!resposta.ok || !nome || !subdominio) {
    throw new Error("não consegui descobrir o endereço do Worker na Cloudflare.");
  }
  return `https://${nome}.${subdominio}.workers.dev`;
}

const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

async function main() {
  const token = limparToken(process.env.DISCORD_TOKEN);
  if (!token) throw new Error("falta o secret DISCORD_TOKEN.");
  const url = await enderecoDoWorker();
  console.log(`🌐 Endereço do Worker: ${url}`);

  const app = await discord(token, "GET", "/applications/@me");
  console.log(`🤖 App do Discord: ${app.name} (${app.id})`);

  if (app.interactions_endpoint_url === url) {
    console.log("✅ O Discord já manda os comandos para o Worker.");
  } else {
    // O Discord testa o endereço na hora; um Worker recém-publicado pode levar um tempinho para responder.
    for (let tentativa = 1; ; tentativa++) {
      try {
        await discord(token, "PATCH", "/applications/@me", { interactions_endpoint_url: url });
        console.log("✅ Pronto: o Discord agora manda os comandos para o Worker.");
        break;
      } catch (erro) {
        if (erro.status !== 400 || tentativa === TENTATIVAS) throw erro;
        console.log(`⏳ O Discord ainda não conseguiu falar com o Worker (${tentativa}/${TENTATIVAS}). Esperando...`);
        await esperar(ESPERA_MS);
      }
    }
  }

  const comandos = JSON.parse(await readFile(new URL("./comandos.json", import.meta.url), "utf8"));
  const registrados = await discord(token, "PUT", `/applications/${app.id}/commands`, comandos);
  console.log(`✅ Comandos registrados: ${registrados.map((comando) => `/${comando.name}`).join(", ")}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((erro) => {
    console.error(`❌ Não consegui ligar os comandos: ${erro.message}`);
    process.exit(1);
  });
}
