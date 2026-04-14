"""
Document loading from Dataiku managed folders, local directories, and upload widgets.
"""
import os
from lib.document_parser import SUPPORTED_EXTENSIONS


def load_documents(folder_name="eval_documents"):
    """
    Load documents from a Dataiku managed folder or local fallback directory.
    Returns dict of {filename: raw_bytes}.
    """
    documents = {}

    # Try Dataiku managed folder first
    try:
        import dataiku
        folder = dataiku.Folder(folder_name)
        for path in folder.list_paths_in_partition():
            ext = os.path.splitext(path)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                with folder.get_download_stream(path) as stream:
                    documents[os.path.basename(path)] = stream.read()
        print(f"Loaded {len(documents)} document(s) from Dataiku folder '{folder_name}'")
    except (ImportError, Exception):
        # Fallback: local directory relative to working directory
        local_folder = os.path.join(os.getcwd(), folder_name)
        if os.path.isdir(local_folder):
            for fname in os.listdir(local_folder):
                ext = os.path.splitext(fname)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    with open(os.path.join(local_folder, fname), "rb") as f:
                        documents[fname] = f.read()
            print(f"Loaded {len(documents)} document(s) from '{local_folder}'")
        else:
            print(f"No '{folder_name}' folder found. Use the upload widget to add files.")

    for name, content in documents.items():
        print(f"  - {name} ({len(content):,} bytes)")

    return documents


def create_upload_widget(documents):
    """
    Display a file upload widget that appends uploaded files to the documents dict.
    Falls back gracefully if ipywidgets is unavailable.
    """
    try:
        import ipywidgets as widgets
        from IPython.display import display

        upload_widget = widgets.FileUpload(
            accept=",".join(SUPPORTED_EXTENSIONS),
            multiple=True,
            description="Upload Documents",
        )
        upload_output = widgets.Output()

        def _on_upload(change):
            with upload_output:
                upload_output.clear_output()
                for f in upload_widget.value:
                    name = f["name"] if isinstance(f, dict) else f.name
                    content = f["content"] if isinstance(f, dict) else f.content
                    if isinstance(content, memoryview):
                        content = bytes(content)
                    documents[name] = content
                    print(f"Uploaded: {name} ({len(content):,} bytes)")

        upload_widget.observe(_on_upload, names="value")
        display(widgets.VBox([upload_widget, upload_output]))

    except ImportError:
        print("ipywidgets not available. Place files in 'eval_documents' folder instead.")
