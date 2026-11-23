<div align="center">

<h1>ai-youtube-video-workflow</h1>

<p>Skills de agente de IA que guiam um criador da identidade do canal até o vídeo publicado no YouTube, uma etapa revisável por vez.</p>

<p><a href="README.md">English</a> | <b>Português</b></p>

<p>
  <a href="https://github.com/fiwon123/ai-youtube-video-workflow/actions/workflows/ci.yml"><img src="https://github.com/fiwon123/ai-youtube-video-workflow/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/fiwon123/ai-youtube-video-workflow/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-proprietary-blue" alt="Licença"></a>
  <img src="https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20WSL2%20%7C%20Windows-4c8bf5" alt="Plataformas">
</p>

</div>

---

## Sumário

- [Sobre](#sobre)
- [Começo rápido](#começo-rápido)
- [Como usar](#como-usar)
- [Onde ficam seus arquivos](#onde-ficam-seus-arquivos)
- [Perguntas frequentes](#perguntas-frequentes)
- [Para desenvolvedores](#para-desenvolvedores)
- [Licença](#licença)

## Sobre

Fazer um vídeo longo para o YouTube com ferramentas de IA significa usar
várias delas à mão: um programa de design para o logo, vídeos de referência
para o estilo, um gerador de imagens para cada cena, um gerador de voz, um
editor de vídeo e os dados do próprio YouTube.

Este projeto conecta essas etapas. Você **conversa com um agente de IA**
(Claude Code, opencode ou Codex) e ele conduz o vídeo uma etapa por vez. Em
cada etapa ele escreve o que você precisa (o roteiro, os prompts das imagens,
o texto da narração, o projeto do Kdenlive, o título e a descrição), diz
exatamente o que fazer na ferramenta externa e confere o que você traz de
volta. Você revisa cada resultado antes de seguir.

**Resumindo:** você traz as ideias e aperta os botões no Canva, Google Flow,
ElevenLabs e Kdenlive; o agente cuida da escrita, dos nomes dos arquivos, do
tempo de cada frase e da montagem da edição.

> Ele **não** usa essas ferramentas por você e **não precisa de chave de
> API**. Nada do que você cria sai do seu computador: tudo fica na pasta
> `channels/`.

## Começo rápido

**1. Tenha o necessário**

| Você precisa de | Para quê |
|---|---|
| Um agente de IA: [Claude Code](https://claude.com/claude-code), opencode ou Codex | ele conduz o processo |
| [Docker](https://docs.docker.com/get-docker/) **ou** Python 3.12 + [uv](https://docs.astral.sh/uv/) | roda a ferramenta `ytflow` |
| Contas no Canva, Google Flow e ElevenLabs | logo/banner, imagens, voz |
| [Kdenlive](https://kdenlive.org/) (gratuito) | a edição final e a renderização |

**2. Baixe o projeto e abra o agente**

```bash
git clone https://github.com/fiwon123/ai-youtube-video-workflow.git
cd ai-youtube-video-workflow

# Com Docker (os agentes já vêm instalados):
make dev-up          # inicia o ambiente; depois Ctrl-C para sair dos logs
make claude-auto     # ou: make opencode-auto / make codex-auto

# Ou sem Docker, com o seu próprio agente instalado:
uv sync
claude               # abra o seu agente nesta pasta
```

No Windows sem WSL2, use `python scripts/dev-up.py dev-up` e
`python scripts/dev-up.py claude-auto` no lugar de `make`.

**3. Diga o que você quer**

Escreva para o agente com palavras simples, em português mesmo. Por exemplo:

> *"Vamos criar um canal novo sobre história antiga."*
>
> *"Vamos continuar."* (ele descobre onde você parou)
>
> *"Comece um vídeo novo sobre as estradas romanas."*

A skill `guide` verifica onde você está (`ytflow status`) e abre a etapa
certa. Você não precisa decorar nenhum comando; o agente roda tudo por você.

## Como usar

Cada etapa abaixo é uma conversa com o agente. Quando gostar do resultado,
diga isso e ele passa para a próxima. Não gostou? Peça mudanças: ele cria uma
**nova versão** (`v2`, `v3`, …) e guarda as anteriores.

### Uma vez por canal

| Etapa | O agente faz | Você faz |
|---|---|---|
| **1. Identidade** | faz algumas perguntas e escreve ideias de nome, descrição e palavras-chave do canal, os tamanhos e o estilo do logo e do banner no Canva, e o modelo de descrição de todos os vídeos | cria o logo e o banner no Canva, salva na pasta de identidade (o agente confere os tamanhos do YouTube) e envia para o YouTube |
| **2. Estilo** | lê 2 a 5 transcrições de vídeos que você gosta e escreve o guia de estilo (gancho, ritmo, estrutura, tom) e a "âncora visual" que entra em todo prompt de imagem | cola as transcrições no chat ou num arquivo |

### Para cada vídeo

| Etapa | O agente faz | Você faz |
|---|---|---|
| **3. Roteiro** | primeiro um esboço, depois o roteiro: uma frase por linha, separadas em capítulos | lê e pede mudanças até gostar |
| **4. Imagens** | um prompt do Google Flow por frase, com nomes como `001_o-rio-ao-amanhecer`, `002_…` | gera cada imagem no Google Flow e baixa; o agente renomeia os downloads (`ytflow images import`) e confere se falta alguma |
| **5. Narração** | o texto para colar no ElevenLabs (e a voz escolhida, guardada para os próximos vídeos) | gera o áudio no ElevenLabs e salva na pasta `audio/` do vídeo; depois o agente marca o tempo de cada frase na voz real (`ytflow align`) |
| **6. Edição** | um projeto do Kdenlive: legendas com caixa, título do capítulo no canto superior esquerdo, fade de entrada e saída, transições e um zoom ou movimento lento em cada imagem, além de um vídeo de prévia | abre o projeto no Kdenlive, assiste, ajusta se quiser e renderiza |
| **7. Publicação** | opções de título, a descrição (com os horários dos capítulos), as tags e o arquivo de legendas | escolhe um título e envia o vídeo para o YouTube |

**Do segundo vídeo em diante é mais rápido.** O primeiro vídeo salva sua voz,
as configurações de edição e o estilo no **kit** do canal, então cada vídeo
novo usa tudo isso automaticamente e fica com a mesma cara do primeiro.

Quer ver um exemplo completo, com os comandos reais e o que eles mostram? Leia
o **[passo a passo](docs/wiki/Walkthrough.md)** (em inglês).

Opcional: para legendas com o tempo mais preciso, rode `uv sync --extra align`
uma vez (instala o faster-whisper). Sem ele, o tempo é estimado por capítulo.

## Onde ficam seus arquivos

Tudo fica em `channels/` (nunca vai para o git):

```text
channels/<canal>/
├── branding/v1/              briefing, guia do Canva, nome/descrição/palavras-chave, seu logo + banner
├── references/               transcrições dos vídeos que você gosta (para a etapa de estilo)
├── kit/v1/                   estilo, âncora visual, voz e configurações de edição do canal
└── videos/<video>/
    ├── script/v1/            o roteiro (e a versão com tempos)
    ├── prompts/v1/           um prompt do Google Flow por frase
    ├── images/               suas imagens: 001_…png, 002_…png, …
    ├── voiceover/v1/         o texto para o ElevenLabs
    ├── audio/                o áudio da sua narração
    ├── timing/v1/            quando cada frase é falada + subtitles.srt
    ├── timeline/v1/          o projeto do Kdenlive (<video>.kdenlive) + preview.mp4
    ├── publish/v1/           título, descrição, tags
    └── package/v1/           tudo o que você cola nas ferramentas, numa pasta só
```

Dica: peça ao agente *"monte o pacote"* (`ytflow package`) para ter numa pasta
só o roteiro com tempos, o texto do ElevenLabs e os prompts do Flow.

## Perguntas frequentes

**Não gostei de um resultado. E agora?**
Diga ao agente o que mudar. Ele cria uma nova versão (`v2`) e guarda a
anterior, para você comparar ou voltar.

**Parei no meio. Como continuo?**
Abra o agente e diga *"vamos continuar"*. Ele lê o `ytflow status` e retoma
de onde você estava.

**Como começo o próximo vídeo?**
Diga *"comece um vídeo novo sobre …"*. A identidade e o estilo já estão
prontos, então ele começa pelo roteiro.

**Quero mudar o estilo ou a voz do canal.**
É só pedir. O agente cria uma nova versão do kit; os vídeos já feitos
continuam com o kit que usaram, e os novos usam o novo.

**Preciso saber os comandos do `ytflow`?**
Não. O agente roda tudo. Se tiver curiosidade, `uv run ytflow --help` lista
os comandos.

**Minhas imagens baixadas vêm com nomes aleatórios.**
Tudo bem: o agente associa cada uma ao seu prompt pelo nome ou pela ordem de
download, e só pergunta sobre as que não conseguir associar.

## Para desenvolvedores

A arquitetura, os comandos de desenvolvimento, a solução de problemas e o que
ainda não foi comprovado estão no **[README em inglês](README.md)**, a partir
de [Architecture](README.md#architecture). As regras que todo agente segue
estão em [AGENTS.md](AGENTS.md).

- **Código**: <https://github.com/fiwon123/ai-youtube-video-workflow>
- **Issues**: <https://github.com/fiwon123/ai-youtube-video-workflow/issues>

## Licença

Proprietária, todos os direitos reservados. Veja [LICENSE](LICENSE).
