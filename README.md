# Árvore de Preços

## Aplicação Streamlit

Instale as dependências, instale o Chromium para o Playwright e inicie a aplicação:

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium
streamlit run app.py
```

A seção **Enviar arquivos e gerar o HTML** recebe as planilhas de Tática (`10. Tatica Cerveja.xlsx`), CTR (`CTR - Árvore de Preços.xlsx`) e Calendário (`Calendario Direta Outubro.xlsx`). Ao iniciar o processamento, os arquivos são salvos em `data/unprocessed` e o app executa os tratamentos, a consolidação em `data/processed/arvore_precos.csv` e a geração do site. Ao final, é possível baixar `arvore_precos_premium.html`, com dados e imagens incorporados. O cadastro mestre `cadastro/de_para.xlsx` e as imagens existentes são reutilizados; eles não são substituídos pelos uploads.

A tela apresenta uma matriz comercial por UF, usando `data/processed/arvore_precos.csv` como fonte de preços, `data/processed/ctr_arvore.csv` como fonte do CTR L3M e `cadastro/de_para.xlsx` como cadastro mestre de produtos e imagens. O tratamento do CTR usa a coluna `m0` para selecionar os três meses mais recentes (`-1`, `-2` e `-3`) e calcula a participação dos Promax da árvore sobre o total de vendas de todos os produtos da UF nesse período. A planilha CTR fornece dados para AM (mercado Manaus), MT, GO, DF, MS, AC e RO; as UFs sem mercado individual na fonte aparecem sem CTR. O agregado regional `NO: AS+C&C` é mapeado para as UFs AC e RO. Os SKUs são agrupados em Lata 269ml, Lata 350ml e Long Neck (incluindo COR 210), ordenados pelo TTC Tática médio disponível entre Atacado e Varejo. Produtos sem preço continuam visíveis no final de cada faixa. Cada imagem de produto mantém uma linha laranja abaixo dela. As miniaturas embutidas na página são convertidas para WebP para reduzir o carregamento. As linhas mostram TTC Tática, PP, TTC Calendário e CTR L3M. PP usa a moda da coluna `TTC mínimo ativação (un.)` da Tática, incluindo zeros; só há PP quando a moda positiva é única e aparece pelo menos duas vezes. O TTC PP do Calendário não é utilizado.

Use a busca por nome, nome abreviado ou Promax para localizar SKUs. O botão **Atualizar** limpa o cache e relê o CSV e o De/Para.

Clique em **Gerar PDF em alta resolução — todas as UFs** para exportar um PDF com uma página para cada UF. O PDF usa texto e elementos vetoriais com as imagens originais, mantendo as dimensões e a formatação do painel. Também é possível selecionar uma UF e clicar em **Gerar PNG de [UF]** para exportar somente aquela árvore, em 8.400 × 5.520 pixels.

As exportações são capturadas do mesmo HTML/CSS da árvore exibida no site, em largura desktop. Logo, imagens grandes dos produtos, linhas e estilos visuais seguem a página, incluindo a categoria **Outros**. Para instalar o navegador e as bibliotecas necessárias em Linux, use `python -m playwright install --with-deps chromium`.

## Página HTML para SharePoint

A interface foi migrada para uma página HTML estática, sem backend ou dependência de Streamlit. A pasta `site` contém `index.html`, `styles.css`, `app.js`, `data.json` e as imagens.

Para gerar novamente a página após atualizar os dados:

```bash
python scripts/build_static_site.py
```

Publique a pasta `site` inteira na biblioteca do SharePoint e abra `index.html`. O navegador carrega os dados e as imagens diretamente dos arquivos locais.

O mesmo comando também gera `site-premium/arvore_precos_premium.html`, um arquivo único com estilos, JavaScript, dados e imagens incorporados. Para compartilhar apenas o site premium, carregue somente esse HTML na biblioteca do SharePoint e compartilhe o link do arquivo. A página é uma cópia dos dados disponíveis no momento da geração; execute o comando novamente e substitua o arquivo no SharePoint quando os dados mudarem.

Em telas de celular, a árvore e os resultados da busca são apresentados em cartões por produto, sem exigir rolagem horizontal. Em computadores, a matriz comercial e a tabela de busca mantêm a apresentação desktop.

O SharePoint da organização precisa permitir a execução de JavaScript em páginas HTML carregadas na biblioteca. Se o arquivo for baixado em vez de exibido ou se o SharePoint bloquear os scripts, será necessário pedir ao administrador uma localização/configuração que permita hospedar essa página.

A busca funciona por nome, nome abreviado ou Promax. A página mantém uma árvore por UF e permite atualizar os registros no momento da visita. O TTC Tática usa o preço de Atacado quando disponível e recorre ao preço de Varejo quando esse é o único canal informado. Nas páginas normal e premium, TTC Tática, PP e Calendário preservam os valores de cada canal; quando diferem são exibidos com **C** (Atacado) e **V** (Varejo), e quando são iguais aparecem uma única vez sem classificação.