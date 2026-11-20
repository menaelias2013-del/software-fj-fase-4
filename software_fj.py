"""Software FJ: gestión en memoria de clientes, servicios y reservas."""

import logging
import re
from abc import ABC, abstractmethod
from decimal import Decimal, DecimalException, ROUND_HALF_UP
from enum import Enum
from typing import overload


class ErrorSoftwareFJ(Exception):
    """Base de los errores previstos por el sistema."""


class DatosInvalidos(ErrorSoftwareFJ):
    """Un dato falta o no cumple las reglas del modelo."""


class ErrorRegistro(ErrorSoftwareFJ):
    """El identificador no existe o ya está en uso."""


class ErrorReserva(ErrorSoftwareFJ):
    """La reserva no puede completar la operación solicitada."""


def texto_requerido(valor, campo):
    """Normaliza espacios y rechaza campos vacíos."""
    if not isinstance(valor, str) or not valor.strip():
        raise DatosInvalidos(f"El campo {campo} es obligatorio.")
    return valor.strip()


def decimal_valido(valor, campo, minimo, maximo):
    """Convierte un dato numérico y comprueba que sea finito y esté en rango."""
    try:
        numero = Decimal(str(valor).strip())
    except DecimalException as error:
        raise DatosInvalidos(f"{campo} debe ser un número.") from error

    if not numero.is_finite() or not minimo <= numero <= maximo:
        raise DatosInvalidos(f"{campo} debe estar entre {minimo} y {maximo}.")
    return numero


def entero_positivo(valor, campo):
    """Valida cantidades enteras para aforo y unidades."""
    if type(valor) is not int or valor <= 0:
        raise DatosInvalidos(f"{campo} debe ser un entero positivo.")
    return valor


class Entidad(ABC):
    """Una entidad del sistema tiene un identificador y una descripción."""

    def __init__(self, codigo):
        self.__codigo = texto_requerido(codigo, "código").upper()

    @property
    def codigo(self):
        return self.__codigo

    @abstractmethod
    def describir(self):
        """Devuelve una descripción de la entidad."""


class Cliente(Entidad):
    """Protege los datos del cliente y los valida al registrarlo."""

    def __init__(self, codigo, nombre, correo, telefono):
        super().__init__(codigo)
        nombre = texto_requerido(nombre, "nombre")
        correo = texto_requerido(correo, "correo")
        telefono = texto_requerido(telefono, "teléfono")

        if len(nombre) < 2 or any(caracter.isdigit() for caracter in nombre):
            raise DatosInvalidos("El nombre debe tener al menos dos caracteres y carecer de dígitos.")
        if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", correo):
            raise DatosInvalidos("El correo debe tener un formato válido.")
        if not re.fullmatch(r"\+?[0-9]{7,15}", telefono):
            raise DatosInvalidos("El teléfono debe tener entre 7 y 15 dígitos.")

        self.__nombre = nombre
        self.__correo = correo
        self.__telefono = telefono

    @property
    def nombre(self):
        return self.__nombre

    @property
    def correo(self):
        return self.__correo

    @property
    def telefono(self):
        return self.__telefono

    def describir(self):
        return f"Cliente {self.codigo} registrado."


class Servicio(Entidad):
    """Define el cálculo común y delega las reglas propias a cada servicio."""

    def __init__(self, codigo, nombre, tarifa_hora, *, disponible=True):
        super().__init__(codigo)
        self._nombre = texto_requerido(nombre, "nombre del servicio")
        self._tarifa = decimal_valido(tarifa_hora, "Tarifa por hora", Decimal("0.01"), 10**9)
        if type(disponible) is not bool:
            raise DatosInvalidos("La disponibilidad debe ser un valor booleano.")
        self.__disponible = disponible

    @property
    def disponible(self):
        return self.__disponible

    @abstractmethod
    def validar_parametros(self, parametros):
        """Comprueba los parámetros requeridos por el servicio."""

    @abstractmethod
    def calcular_base(self, horas, parametros):
        """Calcula el precio antes de descuentos e impuestos."""

    @overload
    def calcular_costo(self, horas, parametros) -> Decimal: ...

    @overload
    def calcular_costo(self, horas, parametros, *, impuesto, descuento=0) -> Decimal: ...

    @overload
    def calcular_costo(self, horas, parametros, *, descuento) -> Decimal: ...

    def calcular_costo(self, horas, parametros, *, impuesto=0, descuento=0) -> Decimal:
        # Los argumentos opcionales dan soporte a las variantes de cálculo en Python.
        duracion = decimal_valido(horas, "Duración en horas", Decimal("0.25"), 168)
        tasa = decimal_valido(impuesto, "Impuesto (%)", 0, 100) / 100
        rebaja = decimal_valido(descuento, "Descuento (%)", 0, 100) / 100
        if not isinstance(parametros, dict):
            raise DatosInvalidos("Los parámetros del servicio deben ser un diccionario.")
        self.validar_parametros(parametros)
        base = self.calcular_base(duracion, parametros)
        total = base * (1 - rebaja) * (1 + tasa)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Sala(Servicio):
    """Cobra por hora y limita el número de asistentes al aforo."""

    def __init__(self, codigo, nombre, tarifa_hora, capacidad, *, disponible=True):
        super().__init__(codigo, nombre, tarifa_hora, disponible=disponible)
        self._capacidad = entero_positivo(capacidad, "Capacidad")

    def describir(self):
        return f"Sala {self.codigo} · {self._nombre} · aforo de {self._capacidad} personas"

    def validar_parametros(self, parametros):
        asistentes = entero_positivo(parametros.get("asistentes"), "Número de asistentes")
        if asistentes > self._capacidad:
            raise DatosInvalidos("El número de asistentes supera el aforo.")

    def calcular_base(self, horas, parametros):
        return self._tarifa * horas


class Equipo(Servicio):
    """Cobra cada unidad por hora y comprueba la cantidad disponible."""

    def __init__(self, codigo, nombre, tarifa_hora, unidades, *, disponible=True):
        super().__init__(codigo, nombre, tarifa_hora, disponible=disponible)
        self._unidades = entero_positivo(unidades, "Unidades disponibles")

    def describir(self):
        return f"Equipo {self.codigo} · {self._nombre} · {self._unidades} unidades"

    def validar_parametros(self, parametros):
        unidades = entero_positivo(parametros.get("unidades"), "Unidades solicitadas")
        if unidades > self._unidades:
            raise DatosInvalidos("La solicitud supera la cantidad disponible para una reserva.")

    def calcular_base(self, horas, parametros):
        return self._tarifa * horas * parametros["unidades"]


class Asesoria(Servicio):
    """Cobra por hora y agrega un cargo fijo por preparación."""

    def __init__(self, codigo, nombre, tarifa_hora, especialidad, cargo_preparacion, *, disponible=True):
        super().__init__(codigo, nombre, tarifa_hora, disponible=disponible)
        self._especialidad = texto_requerido(especialidad, "especialidad")
        self._preparacion = decimal_valido(cargo_preparacion, "Cargo de preparación", 0, 10**9)

    def describir(self):
        return f"Asesoría {self.codigo} · {self._nombre} · {self._especialidad}"

    def validar_parametros(self, parametros):
        tema = texto_requerido(parametros.get("tema"), "tema de la asesoría")
        if len(tema) < 5:
            raise DatosInvalidos("El tema debe tener al menos cinco caracteres.")

    def calcular_base(self, horas, parametros):
        return self._tarifa * horas + self._preparacion


class Estado(Enum):
    PENDIENTE = "pendiente"
    CONFIRMADA = "confirmada"
    PROCESADA = "procesada"
    CANCELADA = "cancelada"


class Reserva(Entidad):
    """Vincula un cliente y un servicio con su duración, costo y estado."""

    def __init__(self, codigo, cliente, servicio, horas, parametros, *, impuesto=0, descuento=0):
        super().__init__(codigo)
        try:
            if not isinstance(cliente, Cliente) or not isinstance(servicio, Servicio):
                raise DatosInvalidos("Se requiere un cliente y un servicio válidos.")
            if not servicio.disponible:
                raise DatosInvalidos("El servicio se encuentra fuera de operación.")

            duracion = decimal_valido(horas, "Duración en horas", Decimal("0.25"), 168)
            costo = servicio.calcular_costo(duracion, parametros, impuesto=impuesto, descuento=descuento)
        except (DatosInvalidos, DecimalException) as error:
            raise ErrorReserva(f"Reserva {self.codigo} inválida. {error}") from error

        self.__cliente = cliente
        self.__servicio = servicio
        self.__duracion = duracion
        self.__costo = costo
        self.__estado = Estado.PENDIENTE

    def describir(self):
        return (
            f"Reserva {self.codigo} {self.__estado.value} · cliente {self.__cliente.codigo}"
            f" · servicio {self.__servicio.codigo} · {self.__duracion:g} h"
            f" · COP {self.__costo:,.2f}"
        )

    def confirmar(self):
        if self.__estado != Estado.PENDIENTE:
            raise ErrorReserva(f"La reserva {self.codigo} debe estar pendiente para confirmarse.")
        if not self.__servicio.disponible:
            raise ErrorReserva("El servicio no está disponible.")
        self.__estado = Estado.CONFIRMADA
        return self

    def procesar(self):
        if self.__estado != Estado.CONFIRMADA:
            raise ErrorReserva(f"La reserva {self.codigo} debe estar confirmada para procesarse.")
        self.__estado = Estado.PROCESADA
        return self

    def cancelar(self):
        if self.__estado not in (Estado.PENDIENTE, Estado.CONFIRMADA):
            raise ErrorReserva(f"No se puede cancelar la reserva {self.codigo} en estado {self.__estado.value}.")
        self.__estado = Estado.CANCELADA
        return self


class SistemaFJ:
    """Administra las colecciones y registra cada operación de la simulación."""

    def __init__(self, bitacora):
        self.__clientes = []
        self.__servicios = []
        self.__reservas = []
        self._bitacora = bitacora

    @staticmethod
    def _guardar(coleccion, entidad):
        if any(existente.codigo == entidad.codigo for existente in coleccion):
            raise ErrorRegistro(f"El código {entidad.codigo} ya está registrado.")
        coleccion.append(entidad)
        return entidad

    @staticmethod
    def _buscar(coleccion, codigo):
        codigo = texto_requerido(codigo, "código").upper()
        for entidad in coleccion:
            if entidad.codigo == codigo:
                return entidad
        raise ErrorRegistro(f"El código {codigo} no está registrado.")

    def registrar_cliente(self, *datos):
        return self._guardar(self.__clientes, Cliente(*datos))

    def crear_servicio(self, tipo, *datos, **opciones):
        if tipo not in (Sala, Equipo, Asesoria):
            raise DatosInvalidos("El tipo de servicio debe ser sala, equipo o asesoría.")
        return self._guardar(self.__servicios, tipo(*datos, **opciones))

    def reservar(self, codigo, codigo_cliente, codigo_servicio, horas, parametros, **tarifas):
        cliente = self._buscar(self.__clientes, codigo_cliente)
        servicio = self._buscar(self.__servicios, codigo_servicio)
        reserva = Reserva(codigo, cliente, servicio, horas, parametros, **tarifas)
        return self._guardar(self.__reservas, reserva)

    def buscar_reserva(self, codigo):
        return self._buscar(self.__reservas, codigo)

    def ejecutar(self, etiqueta, operacion, *datos, **opciones):
        """Informa el resultado y registra los errores sin detener los casos siguientes."""
        try:
            resultado = operacion(*datos, **opciones)
            descripcion = resultado.describir()
        except ErrorSoftwareFJ as error:
            self._bitacora.error("%s | %s", etiqueta, error, exc_info=error.__cause__ is not None)
            print(f"RECHAZADA | {etiqueta} — {error}")
            return False
        except TypeError as error:
            self._bitacora.error("%s | Argumentos faltantes o incorrectos.", etiqueta, exc_info=True)
            print(f"RECHAZADA | {etiqueta} — Argumentos faltantes o incorrectos. {error}")
            return False
        except Exception:
            self._bitacora.exception("%s | Error inesperado.", etiqueta)
            print(f"RECHAZADA | {etiqueta} — Error inesperado. Consulta la bitácora.")
            return False
        else:
            self._bitacora.info("%s | %s", etiqueta, descripcion)
            print(f"CORRECTA  | {etiqueta} — {descripcion}")
            return True
        finally:
            self._bitacora.debug("Fin de la operación %s", etiqueta)


def ejecutar_demostracion(ruta_log="software_fj.log"):
    """Ejecuta casos ficticios y cierra el archivo de registro al terminar."""
    bitacora = logging.Logger("software_fj", level=logging.DEBUG)
    archivo = logging.FileHandler(ruta_log, mode="w", encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    bitacora.addHandler(archivo)

    try:
        sistema = SistemaFJ(bitacora)
        casos = [
            ("Registrar cliente", sistema.registrar_cliente, ("C01", "Ana Demo", "ana@example.com", "3000000000"), {}, True),
            ("Rechazar correo inválido", sistema.registrar_cliente, ("C02", "Luis Demo", "sin-arroba", "3010000000"), {}, False),
            ("Rechazar cliente duplicado", sistema.registrar_cliente, ("C01", "Luis Demo", "luis@example.com", "3010000000"), {}, False),
            ("Crear sala", sistema.crear_servicio, (Sala, "S01", "Sala principal", 50000, 12), {}, True),
            ("Crear equipo", sistema.crear_servicio, (Equipo, "E01", "Proyector", 25000, 4), {}, True),
            ("Crear asesoría", sistema.crear_servicio, (Asesoria, "A01", "Asesoría técnica", 80000, "Sistemas", 20000), {}, True),
            ("Rechazar tarifa negativa", sistema.crear_servicio, (Sala, "S02", "Sala auxiliar", -5000, 10), {}, False),
            ("Rechazar servicio con argumentos faltantes", sistema.crear_servicio, (Equipo, "E04", "Parlante"), {}, False),
            ("Registrar equipo fuera de operación", sistema.crear_servicio, (Equipo, "E02", "Cámara", 30000, 2), {"disponible": False}, True),
            ("Rechazar equipo fuera de operación", sistema.reservar, ("R01", "C01", "E02", 2, {"unidades": 1}), {}, False),
            ("Rechazar exceso de aforo", sistema.reservar, ("R02", "C01", "S01", 2, {"asistentes": 15}), {}, False),
            ("Reservar sala", sistema.reservar, ("R03", "C01", "S01", 2, {"asistentes": 8}), {"impuesto": 19, "descuento": 10}, True),
            ("Rechazar duración inválida", sistema.reservar, ("R04", "C01", "E01", "dos", {"unidades": 1}), {}, False),
            ("Confirmar reserva de sala", lambda: sistema.buscar_reserva("R03").confirmar(), (), {}, True),
            ("Procesar reserva de sala", lambda: sistema.buscar_reserva("R03").procesar(), (), {}, True),
            ("Rechazar cancelación de reserva procesada", lambda: sistema.buscar_reserva("R03").cancelar(), (), {}, False),
            ("Reservar equipos", sistema.reservar, ("R05", "C01", "E01", 1.5, {"unidades": 2}), {}, True),
            ("Cancelar reserva de equipos", lambda: sistema.buscar_reserva("R05").cancelar(), (), {}, True),
            ("Reservar asesoría", sistema.reservar, ("R06", "C01", "A01", 1, {"tema": "Diseño de sistemas"}), {}, True),
            ("Confirmar reserva de asesoría", lambda: sistema.buscar_reserva("R06").confirmar(), (), {}, True),
            ("Procesar reserva de asesoría", lambda: sistema.buscar_reserva("R06").procesar(), (), {}, True),
        ]

        aciertos = 0
        print("SOFTWARE FJ · Simulación de clientes, servicios y reservas")
        for numero, (etiqueta, operacion, datos, opciones, esperado) in enumerate(casos, 1):
            obtenido = sistema.ejecutar(f"{numero:02d}. {etiqueta}", operacion, *datos, **opciones)
            if obtenido == esperado:
                aciertos += 1

        print(f"\nResultado: {aciertos}/{len(casos)} casos con el resultado esperado.")
        print(f"Archivo de eventos y errores: {ruta_log}")
        return aciertos == len(casos)
    finally:
        bitacora.removeHandler(archivo)
        archivo.close()


if __name__ == "__main__":
    if not ejecutar_demostracion():
        raise SystemExit(1)
