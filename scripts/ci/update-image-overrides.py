#!/usr/bin/env python3
import sys
import json
import argparse
from pathlib import Path
from ruamel.yaml import YAML

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--values', required=True, help="Path to values-prod.yaml")
    parser.add_argument('--manifest', required=True, help="Path to approved-images.json")
    parser.add_argument('--excluded-service', action='append', default=[], help="Services explicitly excluded from production")
    parser.add_argument('--summary-output', required=True, help="Path to write the summary JSON")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    values_path = Path(args.values)
    summary_path = Path(args.summary_output)

    if not manifest_path.is_file():
        sys.exit(f"FAIL: Manifest file not found at {manifest_path}")

    with manifest_path.open('r') as f:
        manifest = json.load(f)

    # Validate manifest basic schema
    if manifest.get('schemaVersion') != 1:
        sys.exit("FAIL: Invalid schemaVersion")
    
    if not manifest.get('services'):
        sys.exit("FAIL: Manifest services list is empty")

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    with values_path.open('r') as f:
        doc = yaml.load(f)

    if 'components' not in doc:
        sys.exit("FAIL: 'components' key missing from values-prod.yaml")

    summary = {
        "updated": [],
        "skipped": []
    }

    components = doc['components']

    for service_entry in manifest['services']:
        svc = service_entry['name']
        new_digest = service_entry['digest']
        new_tag = service_entry['tag']

        if svc in args.excluded_service:
            summary['skipped'].append({
                "service": svc,
                "reason": "not deployed in production"
            })
            continue

        if svc not in components:
            sys.exit(f"FAIL: UNKNOWN_PRODUCTION_COMPONENT '{svc}' not found in values-prod.yaml")

        comp = components[svc]
        if 'imageOverride' not in comp:
            comp['imageOverride'] = {}

        old_digest = comp['imageOverride'].get('digest')
        old_tag = comp['imageOverride'].get('tag')

        # Update digest
        comp['imageOverride']['digest'] = new_digest
        tag_field_updated = False

        # Only update tag if it already existed in the yaml or if it's a new imageOverride struct?
        # Specification says: 
        # Case B - component has digest but no tag -> update digest, no tag.
        # Case C - component uses shared default tag -> imageOverride.digest: sha256:new.
        # "Không tự thêm tag nếu tag chưa tồn tại."
        if old_tag is not None:
            comp['imageOverride']['tag'] = new_tag
            tag_field_updated = True

        summary['updated'].append({
            "service": svc,
            "oldDigest": old_digest,
            "newDigest": new_digest,
            "oldTag": old_tag,
            "newTag": new_tag if tag_field_updated else None,
            "tagFieldUpdated": tag_field_updated
        })

    with values_path.open('w') as f:
        yaml.dump(doc, f)

    with summary_path.open('w') as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()
