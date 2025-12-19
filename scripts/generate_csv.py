"""Generate sample CSV files for testing the product importer."""
import csv
import random
import sys
from pathlib import Path


def generate_csv(num_rows: int, output_file: str) -> None:
    """
    Generate a CSV file with random product data.

    Args:
        num_rows: Number of product rows to generate
        output_file: Output CSV file path
    """
    categories = [
        "Electronics",
        "Clothing",
        "Home & Garden",
        "Sports",
        "Books",
        "Toys",
        "Food & Beverage",
        "Beauty",
        "Automotive",
        "Office Supplies",
    ]

    adjectives = [
        "Premium",
        "Deluxe",
        "Standard",
        "Professional",
        "Compact",
        "Portable",
        "Heavy-Duty",
        "Eco-Friendly",
        "Wireless",
        "Smart",
    ]

    products = [
        "Widget",
        "Gadget",
        "Tool",
        "Device",
        "Kit",
        "Set",
        "System",
        "Solution",
        "Accessory",
        "Component",
    ]

    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sku", "name", "description"])

        for i in range(num_rows):
            sku = f"SKU-{i+1:08d}"
            category = random.choice(categories)
            adjective = random.choice(adjectives)
            product = random.choice(products)
            name = f"{adjective} {category} {product}"

            # Generate random description
            description = f"High-quality {adjective.lower()} {product.lower()} designed for {category.lower()}. "
            description += f"Perfect for both professional and personal use. "
            description += f"SKU: {sku}"

            writer.writerow([sku, name, description])

            # Print progress every 10,000 rows
            if (i + 1) % 10000 == 0:
                print(f"Generated {i+1:,} rows...")

    print(f"✅ Successfully generated {num_rows:,} products in {output_file}")


def main():
    """Main function to parse arguments and generate CSV."""
    if len(sys.argv) < 2:
        print("Usage: python generate_csv.py <num_rows> [output_file]")
        print("Example: python generate_csv.py 500000 sample_500k.csv")
        sys.exit(1)

    num_rows = int(sys.argv[1])
    output_file = sys.argv[2] if len(sys.argv) > 2 else f"sample_{num_rows}.csv"

    print(f"Generating CSV with {num_rows:,} rows...")
    generate_csv(num_rows, output_file)


if __name__ == "__main__":
    main()
