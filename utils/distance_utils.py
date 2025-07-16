import numpy as np

def calcular_distancia_real(box1, box2, forma_frame):
    h, w = forma_frame[:2]
    y_base1, y_base2 = box1[3], box2[3]
    f1 = 1 + (y_base1 / h) * 0.7
    f2 = 1 + (y_base2 / h) * 0.7
    altura1 = (box1[3] - box1[1]) * f1
    altura2 = (box2[3] - box2[1]) * f2
    escala = 1.7 / ((altura1 + altura2) / 2)
    cx1, cy1 = (box1[0]+box1[2])/2, (box1[1]+box1[3])/2
    cx2, cy2 = (box2[0]+box2[2])/2, (box2[1]+box2[3])/2
    dpix = np.hypot(cx1-cx2, cy1-cy2)
    fprof = abs(cy1-cy2)/h * 2
    return dpix * escala * (1 + fprof)