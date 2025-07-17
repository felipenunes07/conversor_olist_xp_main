document.addEventListener('DOMContentLoaded', () => {
  const clienteSelect = document.getElementById('cliente-select')
  const usarArquivoExcelBtn = document.getElementById('usar-arquivo-excel-btn')
  const arquivoExcelInput = document.getElementById('arquivo-excel-input')
  const processarBtn = document.getElementById('processar-btn')
  const previewArea = document.getElementById('preview-area')
  const uploadArea = document.getElementById('upload-area')
  const fileNameDisplay = document.getElementById('file-name-display')

  // Elementos da nova seção de upload de mapeamento
  const clientesFileInput = document.getElementById('clientes-file-input')
  const produtosFileInput = document.getElementById('produtos-file-input')
  const clientesFileNameDisplay = document.getElementById(
    'clientes-file-name-display'
  )
  const produtosFileNameDisplay = document.getElementById(
    'produtos-file-name-display'
  )
  const salvarMapeamentoBtn = document.getElementById('salvar-mapeamento-btn')
  const mappingUploadStatus = document.getElementById('mapping-upload-status')

  // Elementos da interface de upload
  const uploadPrompt = document.querySelector('.upload-prompt')
  const fileDisplay = document.querySelector('.file-display')
  const removeFileBtn = document.getElementById('remove-file-btn')
  const spinnerContainer = document.querySelector('.spinner-container')
  const placeholder = previewArea.querySelector('.placeholder')

  let arquivoSelecionado = null
  let arquivoClientesSelecionado = null
  let arquivoProdutosSelecionado = null

  // Funções de UI

  function showFileUI(file) {
    arquivoSelecionado = file
    fileNameDisplay.textContent = file.name
    uploadPrompt.style.display = 'none'
    spinnerContainer.style.display = 'none'
    fileDisplay.style.display = 'flex'
    uploadArea.classList.add('file-selected')
    processarBtn.disabled = false
    previewArea.innerHTML = ''
    previewArea.appendChild(placeholder) // Mostra o placeholder novamente
  }

  function resetUploadUI() {
    arquivoSelecionado = null
    arquivoExcelInput.value = ''
    fileDisplay.style.display = 'none'
    spinnerContainer.style.display = 'none'
    uploadPrompt.style.display = 'flex'
    uploadArea.classList.remove('file-selected')
    processarBtn.disabled = true
    previewArea.innerHTML = ''
    previewArea.appendChild(placeholder)
  }

  function showSpinner() {
    uploadPrompt.style.display = 'none'
    fileDisplay.style.display = 'none'
    spinnerContainer.style.display = 'flex'
  }

  function showFeedback(type, title, message, downloadUrl = null) {
    const iconClass = type === 'success' ? 'success' : 'error'
    let downloadButton = ''
    if (downloadUrl) {
      // Tentar extrair o nome do arquivo do atributo data-filename, se disponível
      let fileName = 'orcamento_convertido_olist.xlsx';
      if (window.lastDownloadedFileName) {
        fileName = window.lastDownloadedFileName;
      }
      downloadButton = `<a href="${downloadUrl}" class="download-btn" download="${fileName}">Baixar Arquivo Novamente</a>`;
    }

    previewArea.innerHTML = `
      <div class="feedback-message">
        <div class="icon ${iconClass}"></div>
        <h3>${title}</h3>
        <p>${message}</p>
        ${downloadButton}
      </div>
    `
  }

  // Função para carregar clientes no select
  function carregarClientes() {
    // Limpa opções existentes, exceto a primeira ("Selecione um cliente...")
    while (clienteSelect.options.length > 1) {
      clienteSelect.remove(1)
    }

    fetch('/clientes')
      .then((response) => {
        if (!response.ok) {
          return response.json().then((err) => {
            throw new Error(
              err.error || 'Erro ao carregar clientes do servidor.'
            )
          })
        }
        return response.json()
      })
      .then((data) => {
        if (data.error) {
          console.error('Erro ao carregar clientes:', data.error)
          // Não sobrescrever a previewArea principal se ela já estiver mostrando algo do processamento
          if (!previewArea.querySelector('#download-link')) {
            previewArea.innerHTML = `<p style='color:red;'>Erro ao carregar lista de clientes: ${data.error}</p>`
          }
          return
        }
        if (data.clientes && data.clientes.length > 0) {
          const clientesOrdenados = data.clientes.sort((a, b) => {
            const nomeA = String(a.Nome)
            const nomeB = String(b.Nome)
            const matchA = nomeA.match(/^CL(\d+)/)
            const matchB = nomeB.match(/^CL(\d+)/)
            const idNumA = matchA ? parseInt(matchA[1], 10) : Infinity
            const idNumB = matchB ? parseInt(matchB[1], 10) : Infinity
            if (idNumA !== Infinity && idNumB !== Infinity)
              return idNumA - idNumB
            if (idNumA !== Infinity) return -1
            if (idNumB !== Infinity) return 1
            return nomeA.localeCompare(nomeB)
          })
          clientesOrdenados.forEach((cliente) => {
            const option = document.createElement('option')
            option.value = cliente.ID
            option.textContent = cliente.Nome
            clienteSelect.appendChild(option)
          })
        } else {
          if (!previewArea.querySelector('#download-link')) {
            previewArea.innerHTML =
              '<p>Nenhum cliente encontrado. Verifique os arquivos de mapeamento.</p>'
          }
        }
      })
      .catch((error) => {
        console.error('Erro na requisição para buscar clientes:', error)
        if (!previewArea.querySelector('#download-link')) {
          previewArea.innerHTML = `<p style='color:red;'>Falha ao buscar clientes: ${error.message}</p>`
        }
      })
  }

  carregarClientes() // Carrega clientes ao iniciar

  usarArquivoExcelBtn.addEventListener('click', () => {
    arquivoExcelInput.click()
  })

  arquivoExcelInput.addEventListener('change', (event) => {
    if (event.target.files.length > 0) {
      showFileUI(event.target.files[0])
    }
  })

  removeFileBtn.addEventListener('click', resetUploadUI)

  uploadArea.addEventListener('dragover', (event) => {
    event.preventDefault()
    if (!arquivoSelecionado) uploadArea.classList.add('dragover')
  })

  uploadArea.addEventListener('dragleave', () => {
    event.preventDefault()
    uploadArea.classList.remove('dragover')
  })

  uploadArea.addEventListener('drop', (event) => {
    event.preventDefault()
    uploadArea.classList.remove('dragover')
    const files = event.dataTransfer.files
    if (files.length > 0) {
      const file = files[0]
      if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
        showFileUI(file)
      } else {
        resetUploadUI()
        showFeedback(
          'error',
          'Arquivo Inválido',
          'Por favor, use apenas arquivos Excel (.xlsx ou .xls).'
        )
      }
    }
  })

  processarBtn.addEventListener('click', () => {
    const clienteId = clienteSelect.value
    if (!clienteId) {
      showFeedback(
        'error',
        'Cliente não selecionado',
        'Por favor, selecione um cliente para continuar.'
      )
      return
    }
    if (!arquivoSelecionado) {
      showFeedback(
        'error',
        'Arquivo não selecionado',
        'Por favor, selecione um arquivo Excel de orçamento.'
      )
      return
    }

    showSpinner()
    previewArea.innerHTML = ''

    const formData = new FormData()
    formData.append('cliente_id', clienteId)
    formData.append('arquivo_excel', arquivoSelecionado)

    fetch('/processar', { method: 'POST', body: formData })
      .then(async (response) => {
        if (!response.ok) {
          const err = await response.json()
          throw new Error(err.error || 'Ocorreu um erro no servidor.')
        }
        // Extrair nome do arquivo do header
        let fileName = 'orcamento_convertido_olist.xlsx';
        const disposition = response.headers.get('Content-Disposition');
        if (disposition && disposition.includes('filename=')) {
          fileName = disposition.split('filename=')[1].replace(/['"]/g, '').trim();
        }
        window.lastDownloadedFileName = fileName;
        const blob = await response.blob()
        if (blob) {
          const url = window.URL.createObjectURL(blob)

          showFeedback(
            'success',
            'Arquivo Processado!',
            'Seu arquivo foi convertido com sucesso.',
            url,
            fileName
          )

          const a = document.createElement('a')
          a.href = url
          a.download = fileName
          document.body.appendChild(a)
          a.click()
          a.remove()

          resetUploadUI()
          clienteSelect.selectedIndex = 0
        }
      })
      .catch((error) => {
        showFeedback('error', 'Erro no Processamento', error.message)
        resetUploadUI()
      })
  })

  // Remover lógica de upload de arquivos de mapeamento
  // (clientesFileInput, produtosFileInput, salvarMapeamentoBtn, mappingUploadStatus, etc.)
})
