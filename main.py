from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Extra
from typing import List, Any
from ortools.sat.python import cp_model

app = FastAPI(title="Generador de Horarios con OR-Tools")

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
def generar_horarios(materias: List[Materia]):

    materias_limpias = []

    for m in materias:

        data = m.dict()

        try:
            semestre = int(m.Semestre)
        except:
            semestre = 0

        grupo = str(m.Grupo)
        profesor = data.get("NombreProfesor", "Sin profesor")
        turno = data.get("Turno", "M")
        nombre = data.get("NombreAsignatura", "")

        horario_limpio = []

        for h in m.Horario:
            if isinstance(h, dict):
                if "dia" in h and "inicio" in h and "fin" in h:
                    horario_limpio.append({
                        "dia": h["dia"],
                        "inicio": int(h["inicio"]),
                        "fin": int(h["fin"])
                    })

        materias_limpias.append({
            **data,
            "Semestre": semestre,
            "Grupo": grupo,
            "NombreProfesor": profesor,
            "Turno": turno,
            "NombreAsignatura": nombre,
            "Horario": horario_limpio
        })

    materias = materias_limpias

    # =========================
    # ORTOOLS
    # =========================
    model = cp_model.CpModel()

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5

    # =========================
    # RESPUESTA FINAL
    # =========================
    resultado = []

    dias_reparto = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]

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
    
        resultado.append(salida)

    return resultado