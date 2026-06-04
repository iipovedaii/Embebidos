# Ejecutar en REPL (con Wi-Fi conectado) si no puedes subir lib/ por USB:
#   >>> import install_umqtt_repl
#   >>> install_umqtt_repl.run()

def run():
    try:
        import mip
    except ImportError:
        print("Este firmware no tiene mip. Cierra el REPL y ejecuta:")
        print("  ./scripts/upload-umqtt.sh")
        return False
    print("[umqtt] instalando via mip...")
    try:
        mip.install("umqtt.simple", "/lib")
        print("[umqtt] OK")
    except Exception as e:
        print("[umqtt] mip fallo:", e)
        print("Usa: ./scripts/upload-umqtt.sh con el REPL cerrado")
        return False
    try:
        from umqtt.simple import MQTTClient

        print("[umqtt] import OK", MQTTClient)
        return True
    except ImportError as e:
        print("[umqtt] import fallo:", e)
        return False
