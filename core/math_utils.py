from pulp import LpProblem, LpMinimize, LpInteger, LpBinary, LpVariable, lpSum, PULP_CBC_CMD

s = 5 # Maximum rating value (scale is from 1 to s)
def calc_delta(ratings, n):
    # Convert ratings to 'delta' values, which represent distances from ideal preference
    return [n - (n * (r - 1) / (s - 1)) for r in ratings]

def solve_profile(vectors, deltas):
    # x[j]: binary user profile preference for feature j (-1 or 1)
    # xl[j]: binary indicator if x[j] == -1
    # xd[j]: binary indicator if x[j] == 1
    # z[i]: slack variable for absolute error between prediction and delta[i]
    n, m = len(vectors[0]), len(vectors)
    prob = LpProblem("p", LpMinimize)
    x  = [LpVariable(f"x{i}", -1, 1, LpInteger) for i in range(n)]
    xl = [LpVariable(f"xl{i}", cat=LpBinary)   for i in range(n)]
    xd = [LpVariable(f"xd{i}", cat=LpBinary)   for i in range(n)]
    z  = [LpVariable(f"z{i}")                  for i in range(m)]
    # Objective: minimize total error across all items
    prob += lpSum(z)
    for i in range(m):
        expr = lpSum(xl[j] if vectors[i][j]==0 else xd[j] for j in range(n))
        prob += expr + z[i] >= deltas[i]
        prob += expr - z[i] <= deltas[i]
    for j in range(n):
        prob += x[j] + 2*xd[j] <= 1; prob += x[j] + xd[j] >= 0
        prob += x[j] - xl[j] <= 0;  prob += x[j] - 2*xl[j] >= -1
    prob.solve(PULP_CBC_CMD(msg=False))
    return [v.varValue for v in x]

def est_rating(profile, features, n):
    # Calculate the number of mismatches between the user profile and the item's features
    delta = sum((u==-1 and r==1) or (u==1 and r==0)
                for u, r in zip(profile, features))
    # Estimate the rating by converting delta to rating scale
    return s - (delta*(s-1)/n)
