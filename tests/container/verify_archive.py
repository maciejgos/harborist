"""Verify the OCI archive contains evidence for the image and source revision."""

import json
import sys
import tarfile
from typing import Any


def verify(path: str, revision: str) -> None:
    with tarfile.open(path) as archive:

        def read(name: str) -> Any:
            stream = archive.extractfile(name)
            if stream is None:
                raise ValueError(f"OCI archive entry is missing: {name}")
            with stream:
                return json.load(stream)

        def blob(digest: str) -> Any:
            return read("blobs/" + digest.replace(":", "/", 1))

        (root,) = read("index.json")["manifests"]
        manifests = blob(root["digest"])["manifests"]
        (image,) = [
            item
            for item in manifests
            if item["platform"]["os"] == "linux"
            and item["platform"]["architecture"] == "amd64"
        ]
        (attestations,) = [
            item
            for item in manifests
            if item.get("annotations", {}).get("vnd.docker.reference.digest")
            == image["digest"]
        ]
        config = blob(blob(image["digest"])["config"]["digest"])
        label = config["config"]["Labels"]["org.opencontainers.image.revision"]
        if label != revision:
            raise ValueError("Image revision does not match the workflow checkout")

        predicates: dict[str, Any] = {}
        for layer in blob(attestations["digest"])["layers"]:
            statement = blob(layer["digest"])
            if not any(
                subject["digest"].get("sha256")
                == image["digest"].removeprefix("sha256:")
                for subject in statement["subject"]
            ):
                raise ValueError("Attestation does not reference the exported image")
            predicates[statement["predicateType"]] = statement["predicate"]

        if "spdxVersion" not in predicates["https://spdx.dev/Document"]:
            raise ValueError("Image SBOM is not SPDX")
        provenance = predicates["https://slsa.dev/provenance/v1"]
        arguments = provenance["buildDefinition"]["externalParameters"]["request"][
            "args"
        ]
        if arguments["label:org.opencontainers.image.revision"] != revision:
            raise ValueError("BuildKit provenance does not match the workflow checkout")


if __name__ == "__main__":
    verify(*sys.argv[1:])
