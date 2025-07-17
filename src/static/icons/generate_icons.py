from PIL import Image
import os

# Abrir a imagem original
original_image = Image.open('icon.png')

# Tamanhos necessários para ícones PWA
icon_sizes = [72, 96, 128, 144, 152, 192, 384, 512]

# Gerar ícones em diferentes tamanhos
for size in icon_sizes:
    resized_image = original_image.resize((size, size), Image.LANCZOS)
    resized_image.save(f'icon-{size}x{size}.png')
    
print("Ícones gerados com sucesso!")
