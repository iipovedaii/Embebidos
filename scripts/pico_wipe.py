# Ejecutar EN la Pico con: mpremote connect PORT run scripts/pico_wipe.py
# Borra todo el contenido del filesystem (archivos y carpetas en la raiz).

import gc
import os


def rm_recursive(path):
    try:
        st = os.stat(path)
    except OSError:
        return
    if st[0] & 0x4000:
        for entry in os.listdir(path):
            child = path + "/" + entry
            rm_recursive(child)
        os.rmdir(path)
    else:
        os.remove(path)


def main():
    for name in list(os.listdir()):
        if name in (".", ".."):
            continue
        print("rm", name)
        rm_recursive(name)
    gc.collect()
    print("WIPED:", os.listdir())


main()
