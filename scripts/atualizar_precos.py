import json
import random
from datetime import datetime

categories = {
    "Alimentos": ["Arroz", "Feijão", "Açúcar", "Café", "Óleo de Soja", "Azeite de Oliva", "Macarrão", "Farinha de Trigo", "Farinha de Mandioca", "Sal", "Molho de Tomate", "Milho de Pipoca", "Sardinha em Lata", "Atum em Lata", "Cereal Matinal"],
    "Laticínios": ["Leite Integral", "Leite Desnatado", "Manteiga", "Margarina", "Queijo Mussarela", "Queijo Prato", "Requeijão", "Iogurte Natural", "Creme de Leite", "Leite Condensado", "Queijo Minas", "Nata"],
    "Carnes & Aves": ["Peito de Frango", "Coxa de Frango", "Carne Bovina Moída", "Alcatra", "Contrafilé", "Picanha", "Bisteca Suína", "Linguiça Toshana", "Salsicha", "Bacon"],
    "Hortifruti": ["Banana Prata", "Maçã Gala", "Laranja Pera", "Tomate", "Cebola", "Batata Inglesa", "Alho", "Cenoura", "Alface Americana", "Mamão Formosa", "Melancia", "Abacaxi", "Limão Taiti", "Abobrinha", "Pimentão Verde"],
    "Bebidas": ["Refrigerante Guaraná", "Refrigerante Cola", "Suco de Laranja 1L", "Água Mineral 500ml", "Água de Coco 1L", "Cerveja Pilsen", "Vinho Tinto", "Chá Gelado", "Energético"],
    "Limpeza": ["Detergente Líquido", "Sabão em Pó", "Sabão Líquido", "Amaciante de Roupas", "Desinfetante", "Água Sanitária", "Lustra Móveis", "Esponja de Aço", "Saco de Lixo 50L", "Limpador Multiuso"],
    "Higiene": ["Papel Higiênico 12un", "Sabonete", "Shampoo", "Condicionador", "Creme Dental", "Escova de Dentes", "Desodorante Roll-on", "Fio Dental", "Protetor Solar", "Algodão"]
}

variations = ["Padrão", "Premium", "Orgânico", "Especial", "Econômico"]

produtos = []
item_id = 1

for cat, items in categories.items():
    for item in items:
        for var in variations[:2]:
            base_price = round(random.uniform(3.50, 65.00), 2)
            produtos.append({
                "id": item_id,
                "nome": f"{item} ({var})",
                "categoria": cat,
                "variacao": var,
                "unidade": random.choice(["kg", "un", "pacote", "1L"]),
                "preco": base_price
            })
            item_id += 1

data = {
    "ultima_atualizacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "total_produtos": len(produtos),
    "produtos": produtos
}

with open("precos.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Catálogo atualizado com sucesso! {len(produtos)} produtos gerados.")
