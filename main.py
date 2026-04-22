from fastapi import FastAPI
from fastapi import UploadFile, File
import pandas as pd
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Extra
from typing import List, Any, Dict
from ortools.sat.python import cp_model
import copy
from typing import Dict
from collections import defaultdict
import logging


logging.basicConfig(
    level=logging.INFO,  # cambia a DEBUG si quieres más detalle
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

logger = logging.getLogger("horarios")

app = FastAPI(title="Generador de Horarios con OR-Tools")

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# MODELO
# =========================
class Materia(BaseModel):
    Semestre: Any
    Grupo: Any
    Horario: List[Any]

    class Config:
        extra = Extra.allow

# -------------------------
# HELPERS (MUY IMPORTANTES)
# -------------------------
def limpiar_texto(valor):
    if pd.isna(valor):
        return ""
    return str(valor).strip()

def limpiar_entero(valor):
    if pd.isna(valor):
        return 0
    try:
        return int(valor)
    except:
        return 0



# =========================
# AULAS REALES ESCUELA
# =========================
AULAS_GENERALES = (
    [f"C-Aula {i}" for i in range(1, 13)] +
    [f"D-Aula {i}" for i in range(1, 13)] +
    [f"E-Aula {i}" for i in range(1, 13)]
)

LAB_QUIMICA = [
    "A-Lab Químico 1",
    "A-Lab Químico 2"
]

SALAS_COMPUTO = [
    "B-Sala Cómputo 1",
    "B-Sala Cómputo 2",
    "B-Sala Cómputo 3"
]

LAB_B = [
    "B-Laboratorio 1"
]


# =========================
# DETECTAR TIPO DE AULA
# =========================
def obtener_aulas_por_materia(nombre):

    nombre = nombre.lower()

    if "comput" in nombre or "digital" in nombre or "inform" in nombre:
        return SALAS_COMPUTO

    elif "quim" in nombre:
        return LAB_QUIMICA

    elif "laboratorio" in nombre:
        return LAB_B

    return AULAS_GENERALES


# =========================
# ENDPOINT
# =========================
@app.post("/generar-horarios")
def generar_horarios(materias: List[Materia]):#
    materias_limpias = []#
    for m in materias:#
        data = m.dict()#
        try:
            semestre = int(m.Semestre)
        except:
            semestre = 0#
        grupo = str(m.Grupo)
        profesor = data.get("NombreProfesor", "Sin profesor")
        turno = data.get("Turno", "M")
        nombre = data.get("NombreAsignatura", "")#
        horario_limpio = []#
        for h in m.Horario:
            if isinstance(h, dict):
                if "dia" in h and "inicio" in h and "fin" in h:
                    horario_limpio.append({
                        "dia": h["dia"],
                        "inicio": int(h["inicio"]),
                        "fin": int(h["fin"])
                    })#
        materias_limpias.append({
            **data,
            "Semestre": semestre,
            "Grupo": grupo,
            "NombreProfesor": profesor,
            "Turno": turno,
            "NombreAsignatura": nombre,
            "Horario": horario_limpio
        })#
    materias = materias_limpias#
    # =========================
    # ORTOOLS
    # =========================
    model = cp_model.CpModel()#
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5#
    # =========================
    # RESPUESTA FINAL
    # =========================
    resultado = []#
    dias_reparto = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]#
    ocupacion_global = {}
    control_grupos = {}
    
    for materia in materias:
    
        clave = f"{materia['Semestre']}-{materia['Grupo']}"
    
        if clave not in ocupacion_global:
            ocupacion_global[clave] = {
                dia: {} for dia in dias_reparto
            }
    
        if clave not in control_grupos:
            control_grupos[clave] = {
                "dia_index": 0,
                "hora": 7 if materia.get("Turno", "M") != "V" else 13
            }
    
        salida = {
            **materia,
            "AulaAsignada": []
        }
    
        aulas_disponibles = obtener_aulas_por_materia(
            materia.get("NombreAsignatura", "")
        )
    
        aula_index = 0
    
        turno = materia.get("Turno", "M")
    
        limite = 17 if turno == "V" else 12
    
        for h in materia["Horario"]:
        
            total_horas = h["fin"] - h["inicio"]
    
            while total_horas > 0:
            
                dia_actual = dias_reparto[
                    control_grupos[clave]["dia_index"] % len(dias_reparto)
                ]
    
                hora_inicio = control_grupos[clave]["hora"]
    
                aula_actual = aulas_disponibles[aula_index % len(aulas_disponibles)]
    
                if aula_actual not in ocupacion_global[clave][dia_actual]:
                    ocupacion_global[clave][dia_actual][aula_actual] = set()
    
                conflicto = hora_inicio in ocupacion_global[clave][dia_actual][aula_actual]
    
                if conflicto:
                    aula_index += 1
                    continue
                
                ocupacion_global[clave][dia_actual][aula_actual].add(hora_inicio)
    
                salida["AulaAsignada"].append({
                    "dia": dia_actual,
                    "inicio": hora_inicio,
                    "fin": hora_inicio + 1,
                    "aula": aula_actual,
                    "profesor": materia.get("NombreProfesor", "")
                })
    
                control_grupos[clave]["hora"] += 1
    
                if control_grupos[clave]["hora"] > limite:
                    control_grupos[clave]["hora"] = 13 if turno == "V" else 7
                    control_grupos[clave]["dia_index"] += 1
    
                total_horas -= 1
    
        resultado.append(salida)#
    return resultado

#
#ARCHIVOS EXCEL
#
@app.post("/transformar-excel")
async def transformar_excel(file: UploadFile = File(...)):
    logger.info(f"POST /transformar-excel called - filename: {getattr(file, 'filename', 'unknown')}")
    logger.info(f"Archivo recibido: {file.filename}")


    df = pd.read_excel(file.file)
    logger.info(f"Filas leídas: {len(df)}") 
    data = df.to_dict(orient="records")

    modelo = transformar_datos(data)

    horarios = generar_horarios_v2(modelo)

    # reutilizas tu función
    return horarios

#
# ENDPOINT PARA DESCOMPONER DATOS Y CREAR ENTIDADES
#
@app.post("/transformar-datos")
def transformar_datos(data: List[Dict]):

    logger.info(f"POST /transformar-datos called - registros recibidos: {len(data)}")
    
    profesores = {}
    materias = {}
    grupos = {}
    asignaciones = []

    for fila in data:

        nombre_prof = limpiar_texto(fila.get("Nombre del profesor"))
        nombre_mat = limpiar_texto(fila.get("Nombre de la asignatura"))
        grupo = limpiar_texto(fila.get("Grupo"))

        logger.debug(f"Fila: Profesor={nombre_prof}, Materia={nombre_mat}, Grupo={grupo}")

        horas = limpiar_entero(fila.get("Horas"))
        semestre = limpiar_entero(fila.get("Semestre"))
        turno = limpiar_texto(fila.get("Turno")) or "M"
        pe = limpiar_texto(fila.get("PE"))

        if nombre_prof and nombre_prof not in profesores:
            profesores[nombre_prof] = {"id": nombre_prof}

        if nombre_mat and nombre_mat not in materias:
            materias[nombre_mat] = {
                "id": nombre_mat,
                "horas_semanales": horas
            }

        grupo_id = f"{pe}-{semestre}-{grupo}" if grupo else ""

        if grupo_id and grupo_id not in grupos:
            grupos[grupo_id] = {
                "id": grupo_id,
                "semestre": semestre,
                "turno": turno,
                "pe": pe
            }

        if nombre_mat and nombre_prof and grupo_id:
            asignaciones.append({
                "materia_id": nombre_mat,
                "profesor_id": nombre_prof,
                "grupo_id": grupo_id,
                "horas_semanales": horas
            })

    logger.info(f"Profesores: {len(profesores)}")
    logger.info(f"Materias: {len(materias)}")
    logger.info(f"Grupos: {len(grupos)}")
    logger.info(f"Asignaciones: {len(asignaciones)}")

    return {
        "profesores": list(profesores.values()),
        "materias": list(materias.values()),
        "grupos": list(grupos.values()),
        "asignaciones": asignaciones
    }

#Endpoint para asignar clases (FUNCIONAL)
#
#ORTOOLS
#
@app.post("/generar-horarios-v2")
def generar_horarios_v2(data: dict):
    logger.info("POST /generar-horarios-v2 called")
    logger.info("Creando variables del modelo...")
    asignaciones = data["asignaciones"]
    grupos = {g["id"]: g for g in data["grupos"]}

    logger.info(f"generar_horarios_v2 - asignaciones: {len(asignaciones)} grupos: {len(grupos)}")

    # -------------------------
    # DETECTAR PERIODO
    # -------------------------
    grupos_sem1 = [g for g in grupos.values() if g["semestre"] == 1]

    if len(grupos_sem1) >= 6:
        periodo = "JULIO_DICIEMBRE"
    else:
        periodo = "ENERO_JUNIO"

    logger.info("PERIODO DETECTADO: %s", periodo)

    #
    #RESTRICCIONES DE PROFESORES
    #

    restricciones_profesores = {

        #  HORARIO DEFINIDO
        "DUARTE ESPARZA LUIS ALEJANDRO": {
            "hora_min": 7,
            "hora_max": 15
        },

        "GARCIA MENDOZA CANDIDO": {
            "hora_min": 7,
            "hora_max": 15
        },

        "HERNANDEZ MENDOZA JORGE MARTIN": {
            "hora_min": 7,
            "hora_max": 15
        },

        "MOLINA RUIZ HÉCTOR DANIEL": {
            "hora_min": 7,
            "hora_max": 15
        },

        "VERA MENDOZA JEINY": {
            "hora_min": 7,
            "hora_max": 17
        },

        "ZAVALA CAMPUZANO ARTURO": {
            "hora_min": 7,
            "hora_max": 15
        },

        #  DESPUÉS DE CIERTA HORA
        "HERNÁNDEZ MONROY NALLELY": {
            "hora_min": 10
        },

        "JIMÉNEZ HERNÁNDEZ HUGO": {
            "hora_min": 10
        },

        "ROJO ESQUIVEL RUBEN": {
            "hora_min": 19
        },

        # DÍAS ESPECÍFICOS
        "MARTINEZ ACOSTA ADOLFO": {
            "dias_permitidos": ["Lunes", "Miercoles", "Viernes"],
            "hora_min": 7,
            "hora_max": 15
        },


        #  HORARIOS COMPLEJOS

        "MARTINES ARANO HILARIO": {
            "horario_por_dia": {
                "Lunes": (11, 19),
                "Martes": (9, 17),
                "Miercoles": (9, 17),
                "Jueves": (9, 17),
                "Viernes": (7, 15)
            },
            "dia_libre": True
        },


        "CASTILLO GOMORA CARMEN CAROLINA": {
            "dias_permitidos": ["Martes", "Jueves"]  # ajusta según semestre
        },

        #complejos/ sin resolver
        "Bornacelli Camargo Jhovani Enrique": {
            "horario_por_dia": {
                "Lunes": (11, 19),
                "Martes": (9, 17),
                "Miercoles": (9, 17),
                "Jueves": (9, 17),
                "Viernes": (7, 15)
                #un dia de descanso
            },
            "dia_libre": True
        },

         "GARCIA VARGAS MA. DE LOURDES ELENA": {
            "horario_por_dia": {
                "Lunes": (9, 17),
                "Martes": (9, 17),
                "Miercoles": (9, 17),
                "Jueves": (9, 17),
                "Viernes": (9, 17)
                #un dia de descanso
            },
            "dia_libre": True
        },

         "MARTINEZ AYALA LIZETH": {
            "horario_por_dia": {
                "Lunes": (9, 17),
                "Martes": (9, 17),
                "Miercoles": (9, 17),
                "Jueves": (9, 17),
                "Viernes": (9, 17)
                #un dia de descanso
            },
            "dia_libre": True
        },

         "MARTINEZ AYALA LIZETH": {
            "horario_por_dia": {
                "Lunes": (7, 17),
                "Martes": (7, 17),
                "Miercoles": (7, 17),
                "Jueves": (7, 17),
                "Viernes": (7, 17)
            }
        },

        
         "ORTA PEÑAFIEL FRANCISCO": {
            "horario_por_dia": {
                "Lunes": (18, 20),
                "Miercoles": (18, 20),
                "Viernes": (18, 20)
            }
        },
        #VALENCIA LÓPEZ DEYANIRA enero-junio - julio-diciembre
        #MONROY LOPEZ CRESCENCIO AARON enero-junio - julio-diciembre
    }

    #
    #RESTRICCIONES DINAMICAS
    #
    restricciones_dinamicas = copy.deepcopy(restricciones_profesores)
    if periodo == "JULIO_DICIEMBRE":

        restricciones_dinamicas["VALENCIA LÓPEZ DEYANIRA"] = {
            "horario_por_dia": {
                "Lunes": (7, 21),
                "Miercoles": (12, 21),
                "Jueves": (7, 21),
                
            }
        }

        restricciones_dinamicas["MONROY LOPEZ CRESCENCIO AARON"] = {
            "horario_por_dia": {
                "Jueves": (7, 21)
            }
        }

    elif periodo == "ENERO_JUNIO":

        restricciones_dinamicas["VALENCIA LÓPEZ DEYANIRA"] = {
            "horario_por_dia": {
                "Lunes": (14, 21),
                "Martes": (20, 21),
                "Miercoles": (20, 21),
                "Jueves": (14, 21),
                "Viernes": (20, 21)
            }
        }

        restricciones_dinamicas["MONROY LOPEZ CRESCENCIO AARON"] = {
            "horario_por_dia": {
                "Martes": (7, 21),
                "Jueves": (7, 21)
            }
        }


    # -------------------------
    # DOMINIO
    # -------------------------
    dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]
    horas = list(range(7, 21))  # 7 a 20

    model = cp_model.CpModel()

    # -------------------------
    # VARIABLES
    # -------------------------
    x = {}
    
    for a_idx, a in enumerate(asignaciones):
        grupo = grupos[a["grupo_id"]]
        turno = grupo["turno"]
        profesor = a["profesor_id"]

        restricciones = restricciones_dinamicas.get(profesor, {})

        for d in dias:
            for h in horas:

                # TURNO
                if turno == "M" and not (7 <= h <= 13):
                    continue
                if turno == "V" and not (13 <= h <= 19):
                    continue
                if turno == "MX" and not (11 <= h <= 19):
                    continue

                #  VALIDAR PROFESOR 
                valido = True

                if "hora_min" in restricciones and h < restricciones["hora_min"]:
                    valido = False

                if "hora_max" in restricciones and h > restricciones["hora_max"]:
                    valido = False

                if "dias_permitidos" in restricciones and d not in restricciones["dias_permitidos"]:
                    valido = False

                if "horario_por_dia" in restricciones:
                    if d in restricciones["horario_por_dia"]:
                        hmin, hmax = restricciones["horario_por_dia"][d]
                        if not (hmin <= h <= hmax):
                            valido = False
                    else:
                        valido = False

                if not valido:
                    continue  #  NO CREAR VARIABLE

                x[(a_idx, d, h)] = model.NewBoolVar(f"x_{a_idx}_{d}_{h}")
    logger.info(f"Total variables creadas: {len(x)}")



    # -------------------------
    # RESTRICCIÓN 1: HORAS SEMANALES
    # -------------------------
    horas_asignadas = []

    # RESTRICCIÓN 1: HORAS SEMANALES EXACTAS (forzar igualdad)
    horas_asignadas = []

    # penalizaciones usadas cuando no hay suficientes slots
    penalizaciones = []

    for a_idx, a in enumerate(asignaciones):

        vars_asignacion = []

        for (ai, d, h), var in x.items():
            if ai == a_idx:
                vars_asignacion.append(var)

        if vars_asignacion:
            disponible = len(vars_asignacion)
            requerido = a["horas_semanales"]

            # siempre permitir asignar hasta lo requerido
            model.Add(sum(vars_asignacion) <= requerido)

            # crear variable de falta = requerido - asignadas (0..requerido)
            falta = model.NewIntVar(0, requerido, f"falta_{a_idx}")
            model.Add(falta == requerido - sum(vars_asignacion))

            if disponible < requerido:
                logger.warning("NO CABEN HORAS: %s requiere %s pero solo %s slots disponibles", a.get("materia_id"), requerido, disponible)

            penalizaciones.append(falta)
    
    # Ya no usamos penalizaciones de falta (horas exactas)
    penalizaciones = []


    #
    # PROPEDEUTICOS
    #
    # -------------------------
    # DETECTAR PROPEDÉUTICOS
    # -------------------------
    propedeuticos = []

    
    for a_idx, a in enumerate(asignaciones):
        nombre = a.get("materia_id", "").upper()
        
        if "PROPEDÉUTICO 1" in nombre:
            #print("✅ DETECTADO:", a)
            propedeuticos.append((a_idx, a))

    #print("TOTAL PROPEDEUTICOS:", len(propedeuticos))

    # -------------------------
    # AGRUPAR PROPEDÉUTICOS POR GRUPO
    # -------------------------
    prop_por_grupo = {}

    for a_idx, a in propedeuticos:
        grupo_id = a["grupo_id"]

        if grupo_id not in prop_por_grupo:
            prop_por_grupo[grupo_id] = []

        prop_por_grupo[grupo_id].append(a_idx)

    # -------------------------
    # AGRUPAR POR SEMESTRE
    # -------------------------
    prop_por_semestre = {}

    for a_idx, a in propedeuticos:
        grupo = grupos[a["grupo_id"]]
        semestre = grupo["semestre"]

        if semestre not in prop_por_semestre:
            prop_por_semestre[semestre] = []

        prop_por_semestre[semestre].append((a_idx, a))

    #print("SEMESTRES CON PROPEDEUTICOS:", list(prop_por_semestre.keys()))

    # -------------------------
    # CREAR VARIABLES DE BLOQUE COMÚN
    # -------------------------
    bloques_prop = {}

    for a_idx, a in propedeuticos:
        for d in ["Lunes", "Martes", "Miercoles", "Jueves"]:
            bloques_prop[(a_idx, d)] = model.NewBoolVar(f"bloque_prop_{a_idx}_{d}")

    # cada propedéutico usa exactamente 2 días
    for a_idx, a in propedeuticos:
        model.Add(
            sum(bloques_prop[(a_idx, d)] for d in ["Lunes", "Martes", "Miercoles", "Jueves"]) == 2
        )


    # -------------------------
    # EVITAR QUE PROPEDÉUTICOS DEL MISMO GRUPO USEN EL MISMO DÍA
    # -------------------------
    for grupo_id, lista in prop_por_grupo.items():

        if len(lista) > 1:

            for d in ["Lunes", "Martes", "Miercoles", "Jueves"]:

                vars_dia = []

                for a_idx in lista:
                    vars_dia.append(bloques_prop[(a_idx, d)])

                model.Add(sum(vars_dia) <= 1)

    # -------------------------
    # SINCRONIZAR + RESTRINGIR PROPEDÉUTICOS
    # -------------------------
    for a_idx, a in propedeuticos:
        grupo = grupos[a["grupo_id"]]
        turno = grupo["turno"]

        # 🔴 1. BLOQUEAR HORAS INVALIDAS (PRIMERO)
        for (ai, d, h), var in x.items():
            if ai == a_idx:

                # Solo lunes a jueves
                if d == "Viernes":
                    model.Add(var == 0)

                if turno == "M":
                    if h not in [11, 12]:
                        model.Add(var == 0)

                elif turno == "V":
                    if h not in [13, 14]:
                        model.Add(var == 0)

        # 🟢 2. SINCRONIZAR BLOQUES (DESPUÉS)
        for d in ["Lunes", "Martes", "Miercoles", "Jueves"]:
            bloque = bloques_prop[(a_idx, d)]

            if turno == "M":
                if (a_idx, d, 11) in x:
                    model.Add(x[(a_idx, d, 11)] == bloque)
                if (a_idx, d, 12) in x:
                    model.Add(x[(a_idx, d, 12)] == bloque)

            elif turno == "V":
                if (a_idx, d, 13) in x:
                    model.Add(x[(a_idx, d, 13)] == bloque)
                if (a_idx, d, 14) in x:
                    model.Add(x[(a_idx, d, 14)] == bloque)


    # -------------------------
    # VARIABLES: TRABAJA POR DÍA (PARA DÍA LIBRE)
    # -------------------------
    trabaja_dia = {}

    for profesor in set(a["profesor_id"] for a in asignaciones):

        if profesor.strip().lower() == "asignada":
            continue

        for d in dias:
            trabaja_dia[(profesor, d)] = model.NewBoolVar(f"trabaja_{profesor}_{d}")

    # -------------------------
    # RESTRICCIÓN 2: NO EMPALME PROFESOR
    # -------------------------
    for d in dias:
        for h in horas:

            for profesor in set(a["profesor_id"] for a in asignaciones):

                
                vars_prof = []

                for (a_idx, dd, hh), var in x.items():
                    if dd == d and hh == h:
                        if asignaciones[a_idx]["profesor_id"] == profesor:
                            # IGNORAR PROPEDÉUTICOS
                            if "PROPEDÉUTICO 1" not in asignaciones[a_idx]["materia_id"]:
                                vars_prof.append(var)

                if vars_prof:
                    model.Add(sum(vars_prof) <= 1)

        # -------------------------
        # RELACIONAR TRABAJA_DIA CON CLASES
        # -------------------------
        for profesor in set(a["profesor_id"] for a in asignaciones):

            if profesor.strip().lower() == "asignada":
                continue

            for d in dias:

                vars_dia = []

                for (a_idx, dd, h), var in x.items():
                    if dd == d and asignaciones[a_idx]["profesor_id"] == profesor:
                        vars_dia.append(var)

                if vars_dia:
                    model.Add(sum(vars_dia) >= trabaja_dia[(profesor, d)])
                    model.Add(sum(vars_dia) <= trabaja_dia[(profesor, d)] * 20)

        # -------------------------
        # RESTRICCIONES DE DISPONIBILIDAD + DÍA LIBRE
        # -------------------------
        for (a_idx, d, h), var in x.items():

            profesor = asignaciones[a_idx]["profesor_id"]

            if profesor.strip().lower() == "asignada":
                continue

            if profesor in restricciones_dinamicas:

                r = restricciones_dinamicas[profesor]

                #  DÍA LIBRE 
                if r.get("dia_libre", False):
                    # si ese día NO trabaja → no puede haber clases
                    model.Add(var <= trabaja_dia[(profesor, d)])

                # días permitidos
                if "dias_permitidos" in r:
                    if d not in r["dias_permitidos"]:
                        model.Add(var == 0)

                #  horario simple
                if "hora_min" in r:
                    if h < r["hora_min"]:
                        model.Add(var == 0)

                if "hora_max" in r:
                    if h >= r["hora_max"]:
                        model.Add(var == 0)

                #  horario por día
                if "horario_por_dia" in r:
                    if d in r["horario_por_dia"]:
                        h_min, h_max = r["horario_por_dia"][d]

                        if h < h_min or h >= h_max:
                            model.Add(var == 0)
                    else:
                        model.Add(var == 0)

        # -------------------------
        # FORZAR DÍA LIBRE SOLO A ALGUNOS PROFESORES
        # -------------------------
        for profesor in set(a["profesor_id"] for a in asignaciones):

            if profesor.strip().lower() == "asignada":
                continue

            if profesor in restricciones_dinamicas:

                r = restricciones_dinamicas[profesor]

                if r.get("dia_libre", False):

                    dias_trabaja = [trabaja_dia[(profesor, d)] for d in dias]

                    # EXACTAMENTE 1 DÍA LIBRE
                    model.Add(sum(dias_trabaja) == 4)
   
    # -------------------------
    # RESTRICCIÓN 3: NO EMPALME GRUPO
    # -------------------------
    for d in dias:
        for h in horas:

            for grupo_id in set(a["grupo_id"] for a in asignaciones):

                vars_grupo = []

                for (a_idx, dd, hh), var in x.items():
                    if dd == d and hh == h:
                        if asignaciones[a_idx]["grupo_id"] == grupo_id:
                            if "PROPEDÉUTICO 1" in asignaciones[a_idx]["materia_id"]:
                                continue
                            vars_grupo.append(var)

                if vars_grupo:
                    model.Add(sum(vars_grupo) <= 1)

   
   #
    # -------------------------
    # BLOQUES DE 2 HORAS (FORZAR DISTRIBUCIÓN EN BLOQUES DE 2 HORAS POR DÍA)
    # -------------------------
    bloques = {}

    for (a_idx, d, h), var in list(x.items()):
        if (a_idx, d, h+1) in x:
            b = model.NewBoolVar(f"bloque_{a_idx}_{d}_{h}")
            # b => ambas horas activas
            model.Add(x[(a_idx, d, h)] + x[(a_idx, d, h+1)] >= 2 * b)
            # si b==1 entonces ambas deben ser 1; podemos también asegurar integridad por objetivo
            bloques[(a_idx, d, h)] = b

    # Para cada asignación, favorecer/forzar que las horas se compongan por bloques de 2 cuando sea posible
    for a_idx, a in enumerate(asignaciones):
        req = a["horas_semanales"]

        # lista de bloques posibles para esta asignación (uno por inicio de hora)
        bloques_posibles = [b for (ai, d, h), b in bloques.items() if ai == a_idx]

        # Si las horas requeridas son pares, intentar organizarlas como bloques de 2: forzar suma(bloques)*2 == req
        if req > 0 and req % 2 == 0 and bloques_posibles:
            model.Add(sum(bloques_posibles) * 2 == req)
            # además, limitar a un bloque por día
            dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]
            for d in dias:
                bloques_dia = [b for (ai, dd, h), b in bloques.items() if ai == a_idx and dd == d]
                if bloques_dia:
                    model.Add(sum(bloques_dia) <= 1)
    
    #
    # variables para materias en un dia
    #
    dias_usados = []

    for a_idx, a in enumerate(asignaciones):
        for d in dias:

            uso_dia = model.NewBoolVar(f"uso_{a_idx}_{d}")

            vars_dia = []

            for (ai, dd, h), var in x.items():
                if ai == a_idx and dd == d:
                    vars_dia.append(var)

            if vars_dia:
                model.Add(sum(vars_dia) >= uso_dia)
                model.Add(sum(vars_dia) <= uso_dia * 10)

                dias_usados.append(uso_dia)
    #
    #Mejora de distribucion de bloques
    #
    horas_solas = []

    for (a_idx, d, h), var in x.items():

        solo = model.NewBoolVar(f"solo_{a_idx}{d}{h}")

        tiene_izq = x.get((a_idx, d, h-1))
        tiene_der = x.get((a_idx, d, h+1))

        if tiene_izq is not None and tiene_der is not None:
            model.Add(solo >= var - tiene_izq - tiene_der)

        elif tiene_izq is not None:
            model.Add(solo >= var - tiene_izq)

        elif tiene_der is not None:
            model.Add(solo >= var - tiene_der)

        else:
            model.Add(solo == var)

        horas_solas.append(solo)
    

    # -------------------------
    # HUECOS EN PROFESORES
    # -------------------------
    huecos_prof = []

    for profesor in set(a["profesor_id"] for a in asignaciones):

        if profesor.strip().lower() == "asignada":
            continue

        for d in dias:
            for h in horas:

                vars_h = []
                vars_izq = []
                vars_der = []

                for (a_idx, dd, hh), var in x.items():
                    if asignaciones[a_idx]["profesor_id"] == profesor:

                        if dd == d and hh == h:
                            vars_h.append(var)

                        if dd == d and hh == h-1:
                            vars_izq.append(var)

                        if dd == d and hh == h+1:
                            vars_der.append(var)

                if vars_h:

                    actual = model.NewBoolVar(f"prof_{profesor}{d}{h}")
                    model.Add(actual == sum(vars_h))

                    izq = model.NewBoolVar(f"prof_{profesor}{d}{h}_izq")
                    if vars_izq:
                        model.Add(izq == sum(vars_izq))
                    else:
                        model.Add(izq == 0)

                    der = model.NewBoolVar(f"prof_{profesor}{d}{h}_der")
                    if vars_der:
                        model.Add(der == sum(vars_der))
                    else:
                        model.Add(der == 0)

                    hueco = model.NewBoolVar(f"hueco_prof_{profesor}{d}{h}")

                    model.Add(hueco >= actual - izq - der)

                    huecos_prof.append(hueco)

    # -------------------------
    # SOLO 1 BLOQUE POR DÍA POR MATERIA 
    # -------------------------
    for a_idx, a in enumerate(asignaciones):
        for d in dias:

            bloques_dia = []

            for h in horas:
                if (a_idx, d, h) in x:

                    # detectar inicio de bloque
                    inicio_bloque = model.NewBoolVar(f"inicio_{a_idx}{d}{h}")

                    if (a_idx, d, h-1) in x:
                        # inicio = 1 si esta hora está activa y la anterior no
                        model.Add(inicio_bloque >= x[(a_idx, d, h)] - x[(a_idx, d, h-1)])
                    else:
                        # primera hora del día
                        model.Add(inicio_bloque == x[(a_idx, d, h)])

                    bloques_dia.append(inicio_bloque)

            if bloques_dia:
                # Relajado: permitir hasta 2 bloques por día por materia
                model.Add(sum(bloques_dia) <= 2)

    model.Maximize(
        sum(x.values()) * 5 +        # cumplir horas
        sum(bloques) * 20  +            #  bloques
        sum(bloques_prop.values()) * 10 -  #  (empuja propedéuticos bien colocados)
        sum(horas_solas) * 25 -        #castigar horas sueltas
        sum(huecos_prof) * 20 +  # castiga huecos de profes fuerte
        sum(dias_usados) * 2 -        # repartir en más días
        sum(penalizaciones) * 100   # castigar faltantes
    )

    # -------------------------
    # RESTRICCIÓN: MAX 3 HORAS SEGUIDAS
    # -------------------------
    for a_idx, a in enumerate(asignaciones):
        for d in dias:
            for h in horas:
                if (a_idx, d, h) in x and (a_idx, d, h+1) in x and (a_idx, d, h+2) in x and (a_idx, d, h+3) in x:

                    model.Add(
                        x[(a_idx, d, h)] +
                        x[(a_idx, d, h+1)] +
                        x[(a_idx, d, h+2)] +
                        x[(a_idx, d, h+3)]
                        <= 3
                    )
    logger.info("Ejecutando solver...")
    # -------------------------
    # SOLVER
    # -------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15

    print("🚀 Iniciando solver")

    status = solver.Solve(model)

    print("✅ Solver terminado")
    print("STATUS:", status)

    print("STATUS:", status)

    if status == cp_model.INFEASIBLE:
        logger.error("MODELO INFACTIBLE")
        # Fallback: intentar la versión alternativa del resolver que puede relajar restricciones
        try:
            logger.info("Intentando fallback con generar_horariov3 debido a infactibilidad...")
            fallback = generar_horariov3(data)
            logger.info("Fallback generado, devolviendo resultado alternativo (long=%s)", len(fallback))
            return fallback
        except Exception as e:
            logger.exception("FALLBACK FALLIDO: %s", e)
    elif status == cp_model.MODEL_INVALID:
        logger.warning("MODELO INVALIDO")
    elif status == cp_model.UNKNOWN:
        logger.warning("NO ENCONTRO SOLUCION EN EL TIEMPO")
    elif status == cp_model.FEASIBLE:
        logger.info("SOLUCION FACTIBLE")
    elif status == cp_model.OPTIMAL:
        logger.info("SOLUCION OPTIMA")
    
    # -------------------------
    # RESULTADO
    # -------------------------
    resultado = []

    if status in [cp_model.FEASIBLE, cp_model.OPTIMAL]:

        temp = {}

        for (a_idx, d, h), var in x.items():
            if solver.Value(var) == 1:

                a = asignaciones[a_idx]
                key = (a_idx, d)

                if key not in temp:
                    temp[key] = []

                temp[key].append(h)

        # convertir a bloques
        for (a_idx, d), horas_lista in temp.items():

            horas_lista.sort()
            a = asignaciones[a_idx]

            #  RECUPERAR TURNO 
            grupo = grupos[a["grupo_id"]]
            turno = grupo["turno"]

            inicio = horas_lista[0]
            fin = inicio

            for i in range(1, len(horas_lista)):
                if horas_lista[i] == fin + 1:
                    fin = horas_lista[i]
                else:
                    resultado.append({
                        "materia": a["materia_id"],
                        "profesor": a["profesor_id"],
                        "grupo": a["grupo_id"],
                        "turno": turno,
                        "dia": d,
                        "hora_inicio": inicio,
                        "hora_fin": fin + 1
                    })
                    inicio = horas_lista[i]
                    fin = inicio

            # último bloque
            resultado.append({
                "materia": a["materia_id"],
                "profesor": a["profesor_id"],
                "grupo": a["grupo_id"],
                "turno": turno,
                "dia": d,
                "hora_inicio": inicio,
                "hora_fin": fin + 1
            })
    # -------------------------
    # VALIDAR HORARIOS DE PROFESORES
    # -------------------------
    errores = []

    for r in resultado:
        profesor = r["profesor"]
        d = r["dia"]
        h_inicio = r["hora_inicio"]
        h_fin = r["hora_fin"]

        if profesor.strip().lower() == "asignada":
            continue

        if profesor in restricciones_profesores:
            reg = restricciones_profesores[profesor]

            for h in range(h_inicio, h_fin):

                # validar días
                if "dias_permitidos" in reg:
                    if d not in reg["dias_permitidos"]:
                        errores.append(f"{profesor} asignado en día no permitido: {d}")

                # validar hora simple
                if "hora_min" in reg:
                    if h < reg["hora_min"]:
                        errores.append(f"{profesor} antes de hora permitida: {h}")

                if "hora_max" in reg:
                    if h >= reg["hora_max"]:
                        errores.append(f"{profesor} después de hora permitida: {h}")

                # validar horario por día
                if "horario_por_dia" in reg:
                    if d in reg["horario_por_dia"]:
                        h_min, h_max = reg["horario_por_dia"][d]

                        if h < h_min or h >= h_max:
                            errores.append(f"{profesor} fuera de horario en {d} a las {h}")
                    else:
                        errores.append(f"{profesor} no trabaja el día {d}")

    # imprimir errores
    if errores:
        logger.error("ERRORES EN HORARIOS:")
        for e in errores:
            logger.error(e)
    else:
        logger.info("TODOS LOS PROFESORES RESPETAN SUS HORARIOS")


    return resultado




#
#Endpoint de prueba (NO FUNCIONAL)
#
@app.post("/generar_horariov3")
def generar_horariov3(data: Dict):

    logger.info("POST /generar_horariov3 called")

    asignaciones = data.get("asignaciones", [])
    
    materias_excluir = ["PRÁCTICAS PROFESIONALES", "SERVICIO SOCIAL"]

    asignaciones = [
        a for a in asignaciones
        if not any(m in a.get("materia_id", "").upper() for m in materias_excluir)
    ]
    grupos_lista = data.get("grupos", [])

    if not asignaciones or not grupos_lista:
        return {"error": "Datos incompletos"}

    grupos = {g["id"]: g for g in grupos_lista}

    dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]
    horas = list(range(7, 21))

    # -------------------------
    # AGRUPAR POR SEMESTRE
    # -------------------------
    asignaciones_por_semestre = defaultdict(list)

    for a in asignaciones:
        grupo = grupos.get(a["grupo_id"])
        if grupo:
            semestre = grupo.get("semestre", 0)
            asignaciones_por_semestre[semestre].append(a)

    # -------------------------
    # FUNCIÓN PARA RESOLVER
    # -------------------------
    def resolver_semestre(asigns):

        logger.info(f"resolver_semestre called - asigns: {len(asigns)}")

        model = cp_model.CpModel()
        x = {}

        # -------------------------
        # DETECTAR PERIODO
        # -------------------------
        grupos_sem1 = [g for g in grupos.values() if g["semestre"] == 1]

        if len(grupos_sem1) >= 6:
            periodo = "JULIO_DICIEMBRE"
        else:
            periodo = "ENERO_JUNIO"

        logger.info("PERIODO DETECTADO: %s", periodo)


        #
        #RESTRICCIONES DE PROFESORES
        #

        restricciones_profesores = {

            # 🟢 HORARIO DEFINIDO
            "DUARTE ESPARZA LUIS ALEJANDRO": {
                "hora_min": 7,
                "hora_max": 15
            },

            "GARCIA MENDOZA CANDIDO": {
                "hora_min": 7,
                "hora_max": 15
            },

            "HERNANDEZ MENDOZA JORGE MARTIN": {
                "hora_min": 7,
                "hora_max": 15
            },

            "MOLINA RUIZ HÉCTOR DANIEL": {
                "hora_min": 7,
                "hora_max": 15
            },

            "VERA MENDOZA JEINY": {
                "hora_min": 7,
                "hora_max": 17
            },

            "ZAVALA CAMPUZANO ARTURO": {
                "hora_min": 7,
                "hora_max": 15
            },

            # 🟢 DESPUÉS DE CIERTA HORA
            "HERNÁNDEZ MONROY NALLELY": {
                "hora_min": 10
            },

            "JIMÉNEZ HERNÁNDEZ HUGO": {
                "hora_min": 10
            },

            "ROJO ESQUIVEL RUBEN": {
                "hora_min": 19
            },

            # 🟢 DÍAS ESPECÍFICOS
            "MARTINEZ ACOSTA ADOLFO": {
                "dias_permitidos": ["Lunes", "Miercoles", "Viernes"],
                "hora_min": 7,
                "hora_max": 15
            },


            # 🟢 HORARIOS COMPLEJOS

            "MARTINES ARANO HILARIO": {
                "horario_por_dia": {
                    "Lunes": (11, 19),
                    "Martes": (9, 17),
                    "Miercoles": (9, 17),
                    "Jueves": (9, 17),
                    "Viernes": (7, 15)
                },
                "dia_libre": True
            },


            "CASTILLO GOMORA CARMEN CAROLINA": {
                "dias_permitidos": ["Martes", "Jueves"]  # ajusta según semestre
            },

            #complejos/ sin resolver
            "Bornacelli Camargo Jhovani Enrique": {
                "horario_por_dia": {
                    "Lunes": (11, 19),
                    "Martes": (9, 17),
                    "Miercoles": (9, 17),
                    "Jueves": (9, 17),
                    "Viernes": (7, 15)
                    #un dia de descanso
                },
                "dia_libre": True
            },

            "GARCIA VARGAS MA. DE LOURDES ELENA": {
                "horario_por_dia": {
                    "Lunes": (9, 17),
                    "Martes": (9, 17),
                    "Miercoles": (9, 17),
                    "Jueves": (9, 17),
                    "Viernes": (9, 17)
                    #un dia de descanso
                },
                "dia_libre": True
            },

            "MARTINEZ AYALA LIZETH": {
                "horario_por_dia": {
                    "Lunes": (9, 17),
                    "Martes": (9, 17),
                    "Miercoles": (9, 17),
                    "Jueves": (9, 17),
                    "Viernes": (9, 17)
                    #un dia de descanso
                },
                "dia_libre": True
            },

            "MARTINEZ AYALA LIZETH": {
                "horario_por_dia": {
                    "Lunes": (7, 17),
                    "Martes": (7, 17),
                    "Miercoles": (7, 17),
                    "Jueves": (7, 17),
                    "Viernes": (7, 17)
                }
            },

            
            "ORTA PEÑAFIEL FRANCISCO": {
                "horario_por_dia": {
                    "Lunes": (18, 20),
                    "Miercoles": (18, 20),
                    "Viernes": (18, 20)
                }
            },
            #VALENCIA LÓPEZ DEYANIRA enero-junio - julio-diciembre
            #MONROY LOPEZ CRESCENCIO AARON enero-junio - julio-diciembre
        }

        #
        #RESTRICCIONES DINAMICAS
        #
        restricciones_dinamicas = copy.deepcopy(restricciones_profesores)
        if periodo == "JULIO_DICIEMBRE":

            restricciones_dinamicas["VALENCIA LÓPEZ DEYANIRA"] = {
                "horario_por_dia": {
                    "Lunes": (7, 21),
                    "Miercoles": (12, 21),
                    "Jueves": (7, 21),
                    
                }
            }

            restricciones_dinamicas["MONROY LOPEZ CRESCENCIO AARON"] = {
                "horario_por_dia": {
                    "Jueves": (7, 21)
                }
            }

        elif periodo == "ENERO_JUNIO":

            restricciones_dinamicas["VALENCIA LÓPEZ DEYANIRA"] = {
                "horario_por_dia": {
                    "Lunes": (14, 21),
                    "Martes": (20, 21),
                    "Miercoles": (20, 21),
                    "Jueves": (14, 21),
                    "Viernes": (20, 21)
                }
            }

            restricciones_dinamicas["MONROY LOPEZ CRESCENCIO AARON"] = {
                "horario_por_dia": {
                    "Martes": (7, 21),
                    "Jueves": (7, 21)
                }
            }

        for a_idx, a in enumerate(asigns):

            grupo = grupos[a["grupo_id"]]
            turno = (grupo.get("turno") or "M").strip().upper()
            profesor = a["profesor_id"]

            restricciones = restricciones_dinamicas.get(profesor, {})

            for d in dias:
                for h in horas:

                    # -------------------------
                    # TURNO FLEXIBLE
                    # -------------------------
                    if turno == "M" and h > 15:
                        continue
                    if turno == "V" and h < 12:
                        continue

                    # -------------------------
                    # IGNORAR "ASIGNADA"
                    # -------------------------
                    if profesor.lower() == "asignada":
                        x[(a_idx, d, h)] = model.NewBoolVar(f"x_{a_idx}_{d}_{h}")
                        continue

                    # -------------------------
                    # VALIDAR PROFESOR
                    # -------------------------
                    valido = True

                    if "hora_min" in restricciones and h < restricciones["hora_min"]:
                        valido = False

                    if "hora_max" in restricciones and h > restricciones["hora_max"]:
                        valido = False

                    if "dias_permitidos" in restricciones and d not in restricciones["dias_permitidos"]:
                        valido = False

                    if "horario_por_dia" in restricciones:
                        if d in restricciones["horario_por_dia"]:
                            hmin, hmax = restricciones["horario_por_dia"][d]
                            if not (hmin <= h <= hmax):
                                valido = False
                        else:
                            valido = False

                    if not valido:
                        continue

                    x[(a_idx, d, h)] = model.NewBoolVar(f"x_{a_idx}_{d}_{h}")

        # -------------------------
        # HORAS EXACTAS
        # -------------------------
        for a_idx, a in enumerate(asigns):

            vars_asignacion = [
                var for (ai, d, h), var in x.items() if ai == a_idx
            ]

            if vars_asignacion:
                model.Add(sum(vars_asignacion) == a["horas_semanales"])

        # -------------------------
        # NO EMPALME GRUPO
        # -------------------------
        grupos_ids = set(a["grupo_id"] for a in asigns)

        for d in dias:
            for h in horas:
                for g in grupos_ids:

                    vars_g = [
                        var for (a_idx, dd, hh), var in x.items()
                        if dd == d and hh == h and asigns[a_idx]["grupo_id"] == g
                    ]

                    if vars_g:
                        model.Add(sum(vars_g) <= 1)
        
        # -------------------------
        # NO REPETIR MATERIA EN EL MISMO DÍA (POR GRUPO)
        # -------------------------
        penalizaciones =[]
        for a_idx, a in enumerate(asigns):

            grupo = a["grupo_id"]

            for d in dias:

                vars_dia = [
                    var for (ai, dd, h), var in x.items()
                    if ai == a_idx and dd == d
                ]

                if vars_dia:
                    # Relajado: permitir varias horas por día para la misma materia (hasta 4)
                    model.Add(sum(vars_dia) <= 4)

                exceso = model.NewIntVar(0, 10, f"exceso_{a_idx}_{d}")
                model.Add(sum(vars_dia) <= 1 + exceso)
                penalizaciones.append(exceso)
        # -------------------------
        # NO EMPALME PROFESOR 🔥 (AQUÍ VA)
        # -------------------------
        profesores = set(a["profesor_id"] for a in asigns)

        for d in dias:
            for h in horas:
                for prof in profesores:

                    if prof.lower() == "asignada":
                        continue  # ignorar estos

                    vars_p = [
                        var for (a_idx, dd, hh), var in x.items()
                        if dd == d and hh == h and asigns[a_idx]["profesor_id"] == prof
                    ]

                    if vars_p:
                        model.Add(sum(vars_p) <= 1)
        
        # -------------------------
        # PROPEDEUTICOS
        # -------------------------

        # DETECTAR
        propedeuticos = []

        for a_idx, a in enumerate(asigns):
            nombre = a.get("materia_id", "").upper()
            if "PROPEDÉUTICO 1" in nombre:
                propedeuticos.append((a_idx, a))


        # VARIABLES DE BLOQUE (día activo o no)
        bloques_prop = {}

        for a_idx, a in propedeuticos:
            for d in dias:
                bloques_prop[(a_idx, d)] = model.NewBoolVar(f"bloque_prop_{a_idx}_{d}")


        # RESTRICCIONES
        for a_idx, a in propedeuticos:

            grupo = grupos[a["grupo_id"]]
            turno = grupo["turno"]

            # 🔴 FORZAR HORARIO FIJO
            for (ai, d, h), var in x.items():
                if ai != a_idx:
                    continue

                # ❌ no viernes
                if d == "Viernes":
                    model.Add(var == 0)

                # TURNOS
                if turno == "M":
                    if h not in [11, 12]:
                        model.Add(var == 0)

                elif turno == "V":
                    if h not in [13, 14]:
                        model.Add(var == 0)


            # 🔥 BLOQUE DE 2 HORAS (CLAVE)
            for d in dias:

                bloque = bloques_prop[(a_idx, d)]

                if turno == "M":

                    if (a_idx, d, 11) in x:
                        model.Add(x[(a_idx, d, 11)] == bloque)

                    if (a_idx, d, 12) in x:
                        model.Add(x[(a_idx, d, 12)] == bloque)

                elif turno == "V":

                    if (a_idx, d, 13) in x:
                        model.Add(x[(a_idx, d, 13)] == bloque)

                    if (a_idx, d, 14) in x:
                        model.Add(x[(a_idx, d, 14)] == bloque)



        # -------------------------
        # VARIABLES: TRABAJA POR DÍA
        # -------------------------
        trabaja_dia = {}

        profesores = set(a["profesor_id"] for a in asigns)

        for profesor in profesores:

            if profesor.strip().lower() == "asignada":
                continue

            for d in dias:
                trabaja_dia[(profesor, d)] = model.NewBoolVar(f"trabaja_{profesor}_{d}")


        # -------------------------
        # RELACIONAR TRABAJA_DIA CON CLASES
        # -------------------------
        for profesor in profesores:

            if profesor.strip().lower() == "asignada":
                continue

            for d in dias:

                vars_dia = [
                    var for (a_idx, dd, h), var in x.items()
                    if dd == d and asigns[a_idx]["profesor_id"] == profesor
                ]

                if vars_dia:
                    model.Add(sum(vars_dia) >= trabaja_dia[(profesor, d)])
                    model.Add(sum(vars_dia) <= trabaja_dia[(profesor, d)] * 20)


        # -------------------------
        # APLICAR DÍA LIBRE
        # -------------------------
        for (a_idx, d, h), var in x.items():

            profesor = asigns[a_idx]["profesor_id"]

            if profesor.strip().lower() == "asignada":
                continue

            if profesor in restricciones_dinamicas:

                r = restricciones_dinamicas[profesor]

                if r.get("dia_libre", False):
                    model.Add(var <= trabaja_dia[(profesor, d)])


        # -------------------------
        # FORZAR EXACTAMENTE 1 DÍA LIBRE
        # -------------------------
        for profesor in profesores:

            if profesor.strip().lower() == "asignada":
                continue

            if profesor in restricciones_dinamicas:

                r = restricciones_dinamicas[profesor]

                if r.get("dia_libre", False):

                    dias_trabaja = [trabaja_dia[(profesor, d)] for d in dias]

                    model.Add(sum(dias_trabaja) == 4)

        #

        # -------------------------
        # BLOQUES DE HORAS (MEJORA DE DISTRIBUCIÓN)
        # -------------------------

        # 🔹 BLOQUES DE 2 HORAS
        bloques = []

        for (a_idx, d, h), var in x.items():
            if (a_idx, d, h+1) in x:

                bloque = model.NewBoolVar(f"bloque_{a_idx}_{d}_{h}")

                # bloque = 1 si ambas horas están activas
                model.Add(bloque <= var)
                model.Add(bloque <= x[(a_idx, d, h+1)])
                model.Add(bloque >= var + x[(a_idx, d, h+1)] - 1)

                bloques.append(bloque)


        # 🔹 HORAS SOLAS (penalizar clases aisladas)
        horas_solas = []

        for (a_idx, d, h), var in x.items():

            solo = model.NewBoolVar(f"solo_{a_idx}_{d}_{h}")

            izq = x.get((a_idx, d, h-1))
            der = x.get((a_idx, d, h+1))

            if izq is not None and der is not None:
                model.Add(solo >= var - izq - der)

            elif izq is not None:
                model.Add(solo >= var - izq)

            elif der is not None:
                model.Add(solo >= var - der)

            else:
                model.Add(solo == var)

                horas_solas.append(solo)


      

         

        # -------------------------
        # OBJETIVO (OPTIMIZACIÓN)
        # -------------------------
        model.Maximize(
            sum(x.values()) * 100   # 🔥 MUCHO MÁS PESO
            + sum(bloques) * 5
            - sum(horas_solas) * 1
            #- sum(penalizaciones) * 1
        )

        logger.info("DEBUG REAL DE CAPACIDAD:")

        for a_idx, a in enumerate(asigns):

            grupo = grupos[a["grupo_id"]]
            profesor = a["profesor_id"]

            opciones = [
                (d, h) for (ai, d, h) in x.keys() if ai == a_idx
            ]

           # print(f"{a['materia_id']} | {profesor} | opciones: {len(opciones)} | requiere: {a['horas_semanales']}")

        if len(opciones) < a["horas_semanales"]:
            logger.warning("NO CABE: %s", a.get("materia_id"))
        logger.info("SATURACIÓN REAL:")

        carga = {}
        for a in asigns:
            p = a["profesor_id"]
            carga[p] = carga.get(p, 0) + a["horas_semanales"]

        for p, h in carga.items():
            logger.info("%s %s", p, h)

        # -------------------------
        # SOLVER
        # -------------------------
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30

        logger.info("Resolver semestre - llamando solver")
        status = solver.Solve(model)

        resultado = []

        if status in [cp_model.FEASIBLE, cp_model.OPTIMAL]:

            for (a_idx, d, h), var in x.items():
                if solver.Value(var) == 1:

                    a = asigns[a_idx]
                    grupo = grupos[a["grupo_id"]]

                    resultado.append({
                        "materia": a["materia_id"],
                        "profesor": a["profesor_id"],
                        "grupo": a["grupo_id"],
                        "turno": grupo["turno"],
                        "dia": d,
                        "hora_inicio": h,
                        "hora_fin": h + 1
                    })

        else:
            logger.warning("No se encontró solución para este semestre")

        return resultado


    def unir_bloques(horario):

        from collections import defaultdict

        grupos = defaultdict(list)

        # 🔥 AGRUPAR primero
        for h in horario:
            key = (
                h["grupo"],
                h["materia"],
                h["profesor"],
                h["dia"]
            )
            grupos[key].append(h)

        resultado = []

        # 🔥 PROCESAR cada grupo separado
        for key, items in grupos.items():

            # ordenar por hora_inicio
            items.sort(key=lambda x: x["hora_inicio"])

            inicio = items[0]["hora_inicio"]
            fin = items[0]["hora_fin"]

            for i in range(1, len(items)):

                actual = items[i]

                if actual["hora_inicio"] == fin:
                    # 🔥 CONTINUO → extender bloque
                    fin = actual["hora_fin"]
                else:
                    # 🔴 CORTAR bloque
                    resultado.append({
                        **items[i-1],
                        "hora_inicio": inicio,
                        "hora_fin": fin
                    })

                    inicio = actual["hora_inicio"]
                    fin = actual["hora_fin"]

            # último bloque
            resultado.append({
                **items[-1],
                "hora_inicio": inicio,
                "hora_fin": fin
            })

        return resultado
    

    # -------------------------
    # RESOLVER TODOS LOS SEMESTRES
    # -------------------------
    horario_final = []

    for semestre, asigns in asignaciones_por_semestre.items():
        logger.info("Resolviendo semestre %s", semestre)
        resultado_semestre = resolver_semestre(asigns)
        horario_final.extend(resultado_semestre)

    horario_final = unir_bloques(horario_final)

    # -------------------------
    # HORAS POR GRUPO
    # -------------------------
    horas_por_grupo = {}

    for r in horario_final:
        g = r["grupo"]
        horas_por_grupo[g] = horas_por_grupo.get(g, 0) + (r["hora_fin"] - r["hora_inicio"])

    # -------------------------
    # HORAS SOLICITADAS
    # -------------------------
    horas_solicitadas = {}

    for a in asignaciones:
        g = a["grupo_id"]
        horas_solicitadas[g] = horas_solicitadas.get(g, 0) + a["horas_semanales"]

    logger.info("COMPARACIÓN:")
    for g in horas_solicitadas:
        logger.info("%s -> solicitadas: %s / asignadas: %s", g, horas_solicitadas[g], horas_por_grupo.get(g, 0))

    # -------------------------
    # DEBUG PROFESORES
    # -------------------------
    horas_prof = {}

    for a in asignaciones:  # 🔥 usa todas las asignaciones
        p = a["profesor_id"]

        if p.lower() == "asignada":
            continue  # 🔥 ignorar

        horas_prof[p] = horas_prof.get(p, 0) + a["horas_semanales"]

    for p, h in horas_prof.items():
        if h > 40:
            logger.warning("PROF SOBRECARGADO: %s %s", p, h)

    # -------------------------
    # RESPUESTA FINAL
    # -------------------------
    return horario_final


