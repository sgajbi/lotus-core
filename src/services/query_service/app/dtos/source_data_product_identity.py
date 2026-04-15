from pydantic import Field


def product_name_field(product_name: str):
    return Field(
        product_name,
        description="RFC-0083 source-data product name represented by this response.",
        examples=[product_name],
    )


def product_version_field():
    return Field(
        "v1",
        description="RFC-0083 source-data product version represented by this response.",
        examples=["v1"],
    )
