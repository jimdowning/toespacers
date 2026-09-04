import numpy as np

def rdp(points, epsilon):
    """Ramer-Douglas-Peucker on a polyline of 2D points (list of (x,y)). Returns simplified list."""
    points = np.asarray(points, dtype=float)
    if len(points) < 3:
        return points.tolist()
    start, end = points[0], points[-1]
    line = end - start
    line_len = np.hypot(*line)
    if line_len == 0:
        d = np.hypot(*(points[1:-1]-start).T)
    else:
        # perpendicular distance from each point to the line start-end
        rel = points[1:-1] - start
        cross_z = line[0]*rel[:, 1] - line[1]*rel[:, 0]
        d = np.abs(cross_z) / line_len
    if len(d) == 0:
        return [start.tolist(), end.tolist()]
    idx = np.argmax(d)
    dmax = d[idx]
    if dmax > epsilon:
        left = rdp(points[:idx+2], epsilon)
        right = rdp(points[idx+1:], epsilon)
        return left[:-1] + right
    else:
        return [start.tolist(), end.tolist()]
