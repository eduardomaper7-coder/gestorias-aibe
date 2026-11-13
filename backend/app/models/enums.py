import enum


class EstadoAgente(str, enum.Enum):
    ACTIVO = "activo"          # responde y envía automáticamente
    SIMULACION = "simulacion"  # procesa todo y guarda lo que habría enviado, pero NO envía
    PAUSADO = "pausado"        # no procesa nada nuevo (los correos se guardan igualmente)


class EstadoAlta(str, enum.Enum):
    ACTIVA = "activa"
    BAJA = "baja"


class Rol(str, enum.Enum):
    ADMIN_AIBE = "admin_aibe"          # Aibe: ve y gestiona todas las gestorías
    ADMIN_GESTORIA = "admin_gestoria"  # responsable de una gestoría: configura su perfil
    GESTOR = "gestor"                  # trabajador de una gestoría: consulta conversaciones y casos


class TipoCliente(str, enum.Enum):
    AUTONOMO = "autonomo"
    SOCIEDAD = "sociedad"
    PARTICULAR = "particular"
    OTRO = "otro"


class CategoriaConocimiento(str, enum.Enum):
    SERVICIOS = "servicios"
    NORMAS = "normas"
    HORARIOS = "horarios"
    TONO = "tono"
    FAQ = "faq"
    CALENDARIO = "calendario"
    OTRO = "otro"


class EstadoConexion(str, enum.Enum):
    SIN_PROBAR = "sin_probar"
    OK = "ok"
    ERROR = "error"


class AccesoPrograma(str, enum.Enum):
    SERVIDOR = "servidor"  # lo lee nuestro servidor (API en la nube, fichero subido)
    PUENTE = "puente"      # lo lee el puente instalado en la gestoría


class EstadoConversacion(str, enum.Enum):
    ABIERTA = "abierta"
    RESPONDIDA = "respondida"
    DERIVADA = "derivada"
    CERRADA = "cerrada"


class Direccion(str, enum.Enum):
    ENTRANTE = "entrante"
    SALIENTE = "saliente"


class Autor(str, enum.Enum):
    CLIENTE = "cliente"
    AGENTE = "agente"
    HUMANO = "humano"
    SISTEMA = "sistema"


class EstadoEnvio(str, enum.Enum):
    NO_APLICA = "no_aplica"  # mensajes entrantes
    PENDIENTE = "pendiente"
    ENVIADO = "enviado"
    SIMULADO = "simulado"
    BLOQUEADO = "bloqueado"  # lo frenó una salvaguarda
    ERROR = "error"


class EstadoDerivacion(str, enum.Enum):
    PENDIENTE = "pendiente"
    ATENDIDA = "atendida"


class EstadoEjecucion(str, enum.Enum):
    EN_CURSO = "en_curso"
    OK = "ok"
    ERROR = "error"


class EstadoReceta(str, enum.Enum):
    BORRADOR = "borrador"
    ACTIVA = "activa"
    RETIRADA = "retirada"


class EstadoCorreccion(str, enum.Enum):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
