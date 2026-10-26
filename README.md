# Visão computacional aplicada ao estudo de probabilidade com dois dados

Projeto acadêmico desenvolvido em Python com OpenCV, NumPy e PyQt6. A aplicação captura imagens da webcam, identifica pontos nas faces de dois dados e acompanha as frequências das médias registradas.

## Artigo FETEC

[Baixar o artigo de Adriano Pacheco em Word](docs/Artigo_FETEC_Adriano_Pacheco.docx).

## Arquivos

- `main.py`: aplicação e processamento das imagens.
- `requirements.txt`: dependências para executar o projeto.
- `docs/Artigo_FETEC_Adriano_Pacheco.docx`: artigo da FETEC.

## Como executar

```bash
python -m pip install -r requirements.txt
python main.py
```

Use **Procurar câmeras** para atualizar a lista de dispositivos. A busca testa os índices de câmera de 0 a 9; a webcam pode precisar estar conectada e liberada por outros aplicativos.

Os registros de lançamentos são mantidos em memória durante a execução. A leitura automática depende das condições de iluminação, enquadramento e ajuste dos parâmetros; consulte as limitações discutidas no artigo.
    
