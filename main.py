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
# MODELOS
# =========================
class Materia(BaseModel):
    Semestre: Any
    Grupo: Any
    Horario: List[Any]

    class Config:
        extra = Extra.allow


# =========================
# ENDPOINT PRINCIPAL
# =========================
@app.post("/generar-horarios")
def generar_horarios(materias: List[Materia]):

    materias_limpias = []

    # =========================
    # NORMALIZAR DATOS
    # =========================
    for m in materias:

        data = m.dict()

        try:
            semestre = int(m.Semestre)
        except:
            semestre = 0

        grupo = str(m.Grupo)
        profesor = data.get("NombreProfesor", "Sin profesor")
        turno = data.get("Turno", "M")

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
            "Horario": horario_limpio
        })

    materias = materias_limpias

    # =========================
    # ORTOOLS
    # =========================
    model = cp_model.CpModel()

    aulas = [f"Aula {i}" for i in range(1, 11)]

    asignaciones = []

    for i, materia in enumerate(materias):
        for j, h in enumerate(materia["Horario"]):
            aula_var = model.NewIntVar(0, len(aulas)-1, f"aula_{i}_{j}")
            asignaciones.append((i, j, aula_var))

    for i1, j1, var1 in asignaciones:
        for i2, j2, var2 in asignaciones:

            if (i1, j1) >= (i2, j2):
                continue

            h1 = materias[i1]["Horario"][j1]
            h2 = materias[i2]["Horario"][j2]

            if h1["dia"] == h2["dia"]:
                solapan = not (
                    h1["fin"] <= h2["inicio"] or h2["fin"] <= h1["inicio"]
                )

                if solapan:
                    model.Add(var1 != var2)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5

    status = solver.Solve(model)

    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("OR-Tools no encontró solución exacta, usando distribución manual")

    # =========================
    # RESPUESTA FINAL
    # =========================
    resultado = []

    dias_reparto = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]

    ocupacion_global = {}

    for i, materia in enumerate(materias):

        clave = f"{materia['Semestre']}-{materia['Grupo']}"

        if clave not in ocupacion_global:
            ocupacion_global[clave] = {dia: set() for dia in dias_reparto}

        salida = {
            **materia,
            "AulaAsignada": []
        }

        aula_index = i % len(aulas)

        turno = materia.get("Turno", "M")

        for j, h in enumerate(materia["Horario"]):

            total_horas = h["fin"] - h["inicio"]

            bloques = []

            while total_horas > 0:
                horas_dia = min(2, total_horas)
                bloques.append(horas_dia)
                total_horas -= horas_dia

            for b, horas_bloque in enumerate(bloques):

                dia_actual = dias_reparto[(i + b) % len(dias_reparto)]

                # =========================
                # HORARIO POR TURNO
                # =========================
                if turno == "V":
                    hora_inicio = 13
                    limite = 17
                else:
                    hora_inicio = 7
                    limite = 11

                while hora_inicio <= limite:

                    conflicto = False

                    for offset in range(horas_bloque):
                        if (hora_inicio + offset) in ocupacion_global[clave][dia_actual]:
                            conflicto = True
                            break

                    if not conflicto:
                        break

                    hora_inicio += 1

                if hora_inicio > limite:
                    continue

                for offset in range(horas_bloque):

                    hora_actual = hora_inicio + offset

                    ocupacion_global[clave][dia_actual].add(hora_actual)

                    salida["AulaAsignada"].append({
                        "dia": dia_actual,
                        "inicio": hora_actual,
                        "fin": hora_actual + 1,
                        "aula": aulas[aula_index],
                        "profesor": materia.get("NombreProfesor", "")
                    })

        resultado.append(salida)

    return resultado