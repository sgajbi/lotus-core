from scripts.release.prebuild_ci_images import SERVICE_BUILDS
from scripts.release.write_image_build_matrix import build_matrix


def test_release_matrix_is_derived_from_source_owned_service_builds() -> None:
    matrix = build_matrix()

    assert [entry["service"] for entry in matrix["include"]] == list(SERVICE_BUILDS)
    assert len(matrix["include"]) == 13
    for entry in matrix["include"]:
        local_tag, dockerfile = SERVICE_BUILDS[entry["service"]]
        assert entry["image_name"] == local_tag.removeprefix("lotus-core/").removesuffix(":local")
        assert entry["dockerfile"] == dockerfile
