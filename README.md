# 🛒 MercadoVoz — Lista de Compras PWA por Voz & WhatsApp
> 🚀 **Acesse o aplicativo:** [lista.trajano.dev.br](https://lista.trajano.dev.br)
> 
O **MercadoVoz** é um **Progressive Web App (PWA)** leve, rápido e 100% em português brasileiro, desenvolvido para simplificar a criação e o controle de listas de compras de supermercado pelo celular ou computador. Com reconhecimento de voz nativo (`Web Speech API`), gestão de múltiplas listas com espelhamento de compras anteriores, base integrada de preços médios do varejo brasileiro e exportação formatada direto para o **WhatsApp**, o aplicativo funciona sem necessidade de login ou banco de dados externo.

## ✨ Funcionalidades Principais

* 🎙️ **Adição por Voz Inteligente (`pt-BR`):** Fale frases corridas e naturais como *"2 pacotes de arroz, 3 litros de leite e 1 kg de café"* e o motor de linguagem do aplicativo separa múltiplos itens, converte números falados por extenso (*um, dois, três, meia dúzia*) e identifica unidades e categorias automaticamente.
* 🗂️ **Múltiplas Listas & Espelhamento de Compras:** Crie quantas listas quiser (*Compras do Mês*, *Feira da Semana*, *Churrasco*), alterne entre elas instantaneamente e use a função **Espelhar** para clonar todos os itens de uma lista antiga em uma nova compra com apenas um toque.
* 💰 **Cálculo Automático & Base de Preços Médios:** Conta com catálogo integrado de produtos essenciais de supermercado (*Mercearia*, *Laticínios*, *Açougue*, *Padaria*, *Hortifrúti*, *Bebidas*, *Limpeza* e *Higiene*), calculando em tempo real os indicadores **Total da Lista**, **Itens**, **No Carrinho** e **Falta Comprar**.
* 💲 **Controle Rápido no Corredor do Mercado:** Marque itens já colocados no carrinho, filtre entre *Todos*, *A Comprar* e *No Carrinho*, pesquise produtos em tempo real e ajuste quantidades (`+` / `-`) ou o preço unitário da prateleira (`💲`).
* 📲 **Compartilhamento Formatado no WhatsApp:** Gera automaticamente uma mensagem organizada com emojis de status (`✅` comprado / `⬜` pendente), quantidades, valores parciais e soma total, permitindo copiar o texto ou enviar direto para qualquer contato no WhatsApp.
* 📦 **PWA Instalável & Persistência Offline:** Suporte completo a instalação na tela inicial no **Android** e **iOS**, cache offline via `Service Worker` e salvamento automático no navegador via `localStorage` (`mercadovoz_clean_v4`).
* 🔊 **Feedback Sonoro Nativo:** Emite confirmação auditiva suave sintetizada via `Web Audio API` ao adicionar produtos ou criar novas listas, com botão rápido para silenciar (`🔊` / `🔇`) no cabeçalho.

## 🛠️ Arquitetura e Tecnologias Utilizadas

| Camada / Recurso | Tecnologia / API | Papel na Aplicação |
| :--- | :--- | :--- |
| **Interface & Layout** | HTML5 Semântico + CSS Grid / Flexbox | Layout mobile-first responsivo sem rolagem horizontal (`overflow-x: hidden`), com barra fixa inferior e cartões adaptáveis |
| **Lógica & Estado** | JavaScript Vanilla (ES6+) | Gerenciamento reativo de múltiplas listas, filtros por aba, busca instantânea e cálculos financeiros em `BRL` |
| **Reconhecimento de Voz** | `Web Speech API` (`SpeechRecognition`) | Captura contínua de voz em `pt-BR` com transcrição em tempo real (`interimResults`) e conversão para itens da lista |
| **Efeitos Sonoros** | `Web Audio API` (`AudioContext`) | Síntese de bipes curtos de confirmação (`660 Hz`) direto no navegador, sem depender de arquivos de áudio externos |
| **Armazenamento Local** | `Web Storage API` (`localStorage`) | Persistência instantânea das listas e itens sob a chave `mercadovoz_clean_v4`, preservando os dados mesmo sem internet |
| **Recursos PWA** | Manifesto Web + Service Worker | Instalação na tela inicial, ícone dedicado e funcionamento em tela cheia (`standalone`) |
| **Integração Externa** | Compartilhamento Direto WhatsApp | Formatação automática da lista de compras e envio direto para números com DDD brasileiro (`+55`) |

## 🗣️ Como Funciona o Reconhecimento de Voz e Texto

O interpretador do **MercadoVoz** aceita tanto comandos de voz quanto digitação manual separada por vírgulas ou pela conjunção *"e"*. Veja exemplos práticos de como as frases são processadas:

| Frase Falada ou Digitada | Qtd. Reconhecida | Unidade | Produto Identificado no Catálogo | Categoria Automática |
| :--- | :---: | :---: | :--- | :--- |
| `"2 pacotes de arroz"` | `2` | `pct` | Arroz Tipo 1 (5kg) | Mercearia |
| `"três litros de leite"` | `3` | `L` | Leite UHT Integral (1L) | Laticínios |
| `"1 kg de café"` | `1` | `pct` | Café Torrado e Moído (500g) | Mercearia |
| `"uma dúzia de ovos"` | `1` | `dz` | Ovos Brancos (Dúzia) | Açougue |
| `"2 kg de frango"` | `2` | `kg` | Filé de Peito de Frango (kg) | Açougue |
| `"sabão em pó e detergente"` | `1` + `1` | `cx` / `un` | Sabão em Pó (1,6kg) + Detergente (500ml) | Limpeza |

> **Dica:** Caso você fale ou digite um produto que não esteja pré-cadastrado no catálogo, o **MercadoVoz** adiciona o item automaticamente na categoria **Outros** com preço médio inicial ajustável no botão `💲`.

## 📲 Como Instalar o App no Celular (PWA)

1. Acesse a aplicação pelo navegador do celular no endereço oficial publicado na Vercel.
2. Toque no botão **📲 Instalar** no canto superior direito ou no aviso automático de instalação:
   * **No Android (Google Chrome / Edge):** Toque em **Instalar Agora** no modal do app ou abra o menu do navegador (**⋮**) e selecione **Instalar aplicativo** / **Adicionar à tela inicial**.
   * **No iPhone / iPad (Safari):** Toque no ícone de **Compartilhar (⬆️)** na barra inferior do Safari e escolha **Adicionar à Tela de Início**.

## 🔄 Fluxo de Desenvolvimento e Deploy

O repositório `dtdias/mercadovoz-pwa` utiliza integração contínua com a **Vercel**:

* **Branch `Dev`:** Ambiente de desenvolvimento e testes de interface, gerando automaticamente um link de Preview na Vercel a cada commit.
* **Branch `main`:** Ambiente de produção atualizado via Pull Request, publicando imediatamente na Vercel.

## 🔗 Links Oficiais

* **Aplicação em Produção (Vercel):** [https://mercadovoz-pwa.vercel.app/](https://mercadovoz-pwa.vercel.app/)
* **Repositório do Projeto (GitHub):** [https://github.com/dtdias/mercadovoz-pwa](https://github.com/dtdias/mercadovoz-pwa)

## 👤 Autor

Desenvolvido por **Daniel Trajano Dias** (`@dtdias`).
