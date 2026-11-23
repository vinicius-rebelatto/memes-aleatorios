// Garante que a conta da Cloudflare tem um endereço *.workers.dev (sem ele o deploy falha).
// Roda no GitHub Actions antes de publicar o Worker. Usa CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID.

const conta = process.env.CLOUDFLARE_ACCOUNT_ID;
const url = `https://api.cloudflare.com/client/v4/accounts/${conta}/workers/subdomain`;
const headers = { Authorization: `Bearer ${process.env.CLOUDFLARE_API_TOKEN}`, "Content-Type": "application/json" };

async function pedir(metodo, corpo) {
  const resposta = await fetch(url, { method: metodo, headers, body: corpo && JSON.stringify(corpo) });
  return { ok: resposta.ok, status: resposta.status, dados: await resposta.json().catch(() => null) };
}

const atual = await pedir("GET");
if (atual.ok && atual.dados?.result?.subdomain) {
  console.log(`✅ Endereço workers.dev: ${atual.dados.result.subdomain}.workers.dev`);
  process.exit(0);
}

const base = (process.env.SUBDOMINIO || process.env.GITHUB_REPOSITORY_OWNER || "memes")
  .toLowerCase()
  .replace(/[^a-z0-9-]/g, "-")
  .replace(/^-+|-+$/g, "")
  .slice(0, 40);
const opcoes = [base, `${base}-memes`, `${base}-${conta.slice(0, 6)}`];
for (const subdominio of opcoes) {
  const criado = await pedir("PUT", { subdomain: subdominio });
  if (criado.ok) {
    console.log(`✅ Criei o endereço ${subdominio}.workers.dev (pode levar alguns minutos para funcionar).`);
    process.exit(0);
  }
  console.log(`⚠️ ${subdominio}.workers.dev não deu (${criado.status}): ${JSON.stringify(criado.dados?.errors ?? [])}`);
}
console.error("❌ Não consegui criar um endereço workers.dev. Abra Workers & Pages no painel da Cloudflare uma vez e rode de novo.");
process.exit(1);
