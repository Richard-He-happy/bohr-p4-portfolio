"""statsx.py - stdlib statistics engine + column profiler (analysis-02). No third
party imports, no I/O; bootstrap seeds from zlib.crc32(label), reruns identical."""
import math,random,re,zlib
VERSION = "1.0.0"
_SALT = "an02"

def _betacf(a, b, x):
  t = 1e-300; qab = a + b; qap = a + 1.0; qam = a - 1.0
  c = 1.0; d = 1.0 - qab * x / qap
  d = t if abs(d) < t else d; d = 1.0 / d; h = d
  for m in range(1, 300):
    m2 = 2 * m
    aa = m * (b - m) * x / ((qam + m2) * (a + m2))
    d = 1.0 + aa * d; d = t if abs(d) < t else d
    c = 1.0 + aa / c; c = t if abs(c) < t else c
    d = 1.0 / d; h *= d * c
    aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
    d = 1.0 + aa * d; d = t if abs(d) < t else d
    c = 1.0 + aa / c; c = t if abs(c) < t else c
    d = 1.0 / d; de = d * c; h *= de
    if abs(de - 1.0) < 3e-16: break
  return h

def betai(a, b, x):
  if x <= 0.0: return 0.0
  if x >= 1.0: return 1.0
  lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
  bt = math.exp(lb + a * math.log(x) + b * math.log(1.0 - x))
  if x < (a + 1.0) / (a + b + 2.0): return bt * _betacf(a, b, x) / a
  return 1.0 - bt * _betacf(b, a, 1.0 - x) / b

def _gser(a, x):
  ap = a; s = 1.0 / a; de = 1.0 / a
  for _ in range(1000):
    ap += 1.0; de *= x / ap; s += de
    if abs(de) < abs(s) * 3e-16: break
  return s * math.exp(-x + a * math.log(x) - math.lgamma(a))

def _gcf(a, x):
  t = 1e-300; b = x + 1.0 - a; c = 1.0 / t; d = 1.0 / b; h = d
  for i in range(1, 1000):
    an = -i * (i - a); b += 2.0; d = an * d + b
    d = t if abs(d) < t else d; c = b + an / c; c = t if abs(c) < t else c
    d = 1.0 / d; de = d * c; h *= de
    if abs(de - 1.0) < 3e-16: break
  return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h

def gammp(a, x):
  if x <= 0.0: return 0.0
  return _gser(a, x) if x < a + 1.0 else 1.0 - _gcf(a, x)

def norm_cdf(z): return 0.5 * math.erfc(-z / math.sqrt(2.0))
def norm_sf2(z): return math.erfc(abs(z) / math.sqrt(2.0))

def norm_ppf(q):
  lo, hi = -10.0, 10.0
  for _ in range(200):
    mid = 0.5 * (lo + hi)
    if norm_cdf(mid) < q: lo = mid
    else: hi = mid
  return 0.5 * (lo + hi)

def t_cdf(t, df):
  if df <= 0: return None
  tail = 0.5 * betai(df / 2.0, 0.5, df / (df + t * t))
  return 1.0 - tail if t > 0 else tail

def t_p(t, df):
  if df <= 0 or t is None: return None
  return betai(df / 2.0, 0.5, df / (df + t * t))

def t_ppf(q, df):
  if not 0.0 < q < 1.0 or df <= 0: return None
  if abs(q - 0.5) < 1e-15: return 0.0
  if q < 0.5:
    v = t_ppf(1.0 - q, df); return -v if v is not None else None
  lo, hi = 0.0, 1.0
  while t_cdf(hi, df) < q and hi < 1e8: hi *= 2.0
  for _ in range(120):
    mid = 0.5 * (lo + hi)
    if t_cdf(mid, df) < q: lo = mid
    else: hi = mid
  return 0.5 * (lo + hi)

def chi2_sf(x, df):
  if x is None or df <= 0: return None
  return max(0.0, 1.0 - gammp(df / 2.0, x / 2.0))

def f_sf(f, d1, d2):
  if f is None or d1 <= 0 or d2 <= 0: return None
  if f <= 0: return 1.0
  return betai(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))

def quantile(s, q):
  n = len(s)
  if n == 0: return None
  if n == 1: return float(s[0])
  h = (n - 1) * q; lo = int(math.floor(h)); hi = min(lo + 1, n - 1)
  return s[lo] + (h - lo) * (s[hi] - s[lo])

def _skew(v, m, sd=None):
  """Adjusted Fisher-Pearson G1; moments use the n-denominator (population) m2/m3."""
  n = len(v)
  if n < 3: return None
  d = [x - m for x in v]; m2 = sum(x * x for x in d) / n
  if m2 <= 0: return None
  return sum(x ** 3 for x in d) / n / m2 ** 1.5 * math.sqrt(n * (n - 1)) / (n - 2)

def _kurt(v, m, sd=None):
  """Bias-corrected excess kurtosis G2 (n-denominator moments)."""
  n = len(v)
  if n < 4: return None
  d = [x - m for x in v]; m2 = sum(x * x for x in d) / n
  if m2 <= 0: return None
  g = sum(x ** 4 for x in d) / n / m2 ** 2 - 3.0
  return ((n + 1) * g + 6.0) * (n - 1) / ((n - 2) * (n - 3))

def mean_ci(v, conf=0.95):
  n = len(v)
  if n < 2: return None
  m = sum(v) / n; sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
  tv = t_ppf(1 - (1 - conf) / 2, n - 1)
  if tv is None: return None
  se = sd / math.sqrt(n); return [m - tv * se, m + tv * se]

def describe(v, conf=0.95):
  n = len(v)
  if n == 0: return {"n": 0}
  m = sum(v) / n
  var = sum((x - m) ** 2 for x in v) / (n - 1) if n > 1 else None
  sd = math.sqrt(var) if var is not None else None
  s = sorted(v); q1 = quantile(s, 0.25); q3 = quantile(s, 0.75)
  return {"n": n, "mean": m, "sum": sum(v), "sd": sd, "var": var,
      "se": (sd / math.sqrt(n)) if sd is not None else None,
      "median": quantile(s, 0.5), "q1": q1, "q3": q3, "iqr": q3 - q1,
      "min": s[0], "max": s[-1], "range": s[-1] - s[0],
      "cv": (sd / m) if (sd is not None and m) else None,
      "skew_g1": _skew(v, m, sd), "kurt_g2": _kurt(v, m, sd),
      "mean_ci": mean_ci(v, conf) if n >= 2 else None,
      "zero_variance": bool(sd == 0) if sd is not None else False,
      "distinct": len(set(v)), "sd_method": "sample SD (n-1)",
      "quantile_method": "linear interpolation (R type 7)"}

def dagostino_k2(v):
  """D'Agostino-Pearson K2 omnibus normality test (n>=8, uses skew+kurtosis)."""
  n = len(v)
  if n < 8: return {"test": "D'Agostino-Pearson K2", "n": n, "valid": False, "reason": "n<8，不适用"}
  m = sum(v) / n; sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
  if not sd: return {"test": "D'Agostino-Pearson K2", "n": n, "valid": False, "reason": "零方差"}
  d = [x - m for x in v]; m2 = sum(x * x for x in d) / n
  g1 = sum(x ** 3 for x in d) / n / m2 ** 1.5
  b2raw = sum(x ** 4 for x in d) / n / m2 ** 2
  y = g1 * math.sqrt((n + 1) * (n + 3) / (6.0 * (n - 2)))
  b2 = 3.0 * (n * n + 27 * n - 70) * (n + 1) * (n + 3) / ((n - 2) * (n + 5) * (n + 7) * (n + 9))
  w2 = -1.0 + math.sqrt(2.0 * (b2 - 1.0))
  if w2 <= 1.0: return {"test": "D'Agostino-Pearson K2", "n": n, "valid": False, "reason": "n 过小"}
  z1 = math.asinh(y / math.sqrt(2.0 / (w2 - 1.0))) / math.sqrt(0.5 * math.log(w2))
  e = 3.0 * (n - 1) / (n + 1)
  vb = 24.0 * n * (n - 2) * (n - 3) / ((n + 1) ** 2 * (n + 3) * (n + 5))
  if vb <= 0: return {"test": "D'Agostino-Pearson K2", "n": n, "valid": False, "reason": "n 过小"}
  x = (b2raw - e) / math.sqrt(vb)
  sb1 = (6.0 * (n * n - 5 * n + 2) / ((n + 7) * (n + 9))) * math.sqrt(6.0 * (n + 3) * (n + 5) / (n * (n - 2) * (n - 3)))
  a = 6.0 + 8.0 / sb1 * (2.0 / sb1 + math.sqrt(1.0 + 4.0 / (sb1 * sb1)))
  den = 1.0 + x * math.sqrt(2.0 / (a - 4.0))
  if den == 0: return {"test": "D'Agostino-Pearson K2", "n": n, "valid": False, "reason": "数值不稳定"}
  t2 = math.copysign(abs((1.0 - 2.0 / a) / abs(den)) ** (1.0 / 3.0), den)
  z2 = (1.0 - 2.0 / (9.0 * a) - t2) / math.sqrt(2.0 / (9.0 * a))
  k2 = z1 * z1 + z2 * z2; p = chi2_sf(k2, 2)
  return {"test": "D'Agostino-Pearson K2", "n": n, "valid": True, "statistic": k2, "df": 2,
      "p_value": p, "skew_b1": g1, "kurt_b2": b2raw, "normal_at_0.05": bool(p is not None and p >= 0.05),
      "note": "K2~chi2(2); p>=0.05 不拒绝正态"}

def levene(groups):
  """Median-centred Levene / Brown-Forsythe: robust to skew, tests scale only."""
  k = len(groups)
  if k < 2 or any(len(g) < 2 for g in groups):
    return {"test": "Levene-Brown-Forsythe", "valid": False, "reason": "每组需 >=2 观测"}
  zs = [[abs(x - quantile(sorted(g), 0.5)) for x in g] for g in groups]
  ni = [len(z) for z in zs]; N = sum(ni)
  if N - k <= 0: return {"test": "Levene-Brown-Forsythe", "valid": False, "reason": "自由度不足"}
  grand = sum(sum(z) for z in zs) / N
  zi = [sum(z) / len(z) for z in zs]
  num = sum(n * (m - grand) ** 2 for n, m in zip(ni, zi))
  den = sum(sum((x - m) ** 2 for x in z) for z, m in zip(zs, zi))
  if den <= 0: return {"test": "Levene-Brown-Forsythe", "valid": False, "reason": "各组绝对离差为 0（零方差）"}
  W = ((N - k) / (k - 1.0)) * (num / den); p = f_sf(W, k - 1, N - k)
  return {"test": "Levene-Brown-Forsythe (median-centred)", "valid": True, "statistic": W,
      "df1": k - 1, "df2": N - k, "p_value": p, "equal_variance_at_0.05": bool(p is not None and p >= 0.05)}

def d_ci(d, n1, n2, conf=0.95):
  """Hedges-Olkin large-sample CI for a standardized mean difference."""
  if d is None or n1 < 2 or n2 < 2: return None
  se = math.sqrt((n1 + n2) / (n1 * n2) + d * d / (2.0 * (n1 + n2)))
  z = 1.959963984540054 if conf == 0.95 else norm_ppf((1 + conf) / 2)
  return [d - z * se, d + z * se]

def ttest_ind(x, y, conf=0.95):
  """Student (pooled) and Welch t on the same difference; both kept auditable."""
  n1, n2 = len(x), len(y)
  if n1 < 2 or n2 < 2: return {"valid": False, "reason": "每组至少 2 个观测"}
  m1, m2 = sum(x) / n1, sum(y) / n2
  s1 = math.sqrt(sum((v - m1) ** 2 for v in x) / (n1 - 1))
  s2 = math.sqrt(sum((v - m2) ** 2 for v in y) / (n2 - 1))
  diff = m1 - m2
  out = {"valid": True, "n1": n1, "n2": n2, "mean1": m1, "mean2": m2, "sd1": s1, "sd2": s2,
      "diff": diff, "conf": conf, "estimate_name": "mean1 - mean2"}
  if s1 == 0 and s2 == 0:
    out.update({"valid": False, "reason": "两组零方差，均值差 SE=0，t 检验无定义"}); return out
  dfp = n1 + n2 - 2
  sp = math.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / dfp)
  if sp > 0:
    sep = sp * math.sqrt(1.0 / n1 + 1.0 / n2); t = diff / sep
    tv = t_ppf(1 - (1 - conf) / 2, dfp); d = diff / sp
    out["student"] = {"method": "Student two-sample t-test (pooled SD)", "method_id": "t_student",
             "statistic": t, "df": dfp, "p_value": t_p(t, dfp), "se": sep, "pooled_sd": sp,
             "estimate_ci": [diff - tv * sep, diff + tv * sep], "cohen_d": d,
             "effect_ci": d_ci(d, n1, n2, conf), "df_method": "n1+n2-2 (equal variance)"}
  sew = math.sqrt(s1 ** 2 / n1 + s2 ** 2 / n2)
  if sew > 0:
    tw = diff / sew
    den = s1 ** 4 / (n1 ** 2 * (n1 - 1)) + s2 ** 4 / (n2 ** 2 * (n2 - 1))
    dfw = (s1 ** 2 / n1 + s2 ** 2 / n2) ** 2 / den if den > 0 else None
    if dfw:
      tvw = t_ppf(1 - (1 - conf) / 2, dfw)
      dw = diff / sp if sp > 0 else None
      out["welch"] = {"method": "Welch two-sample t-test", "method_id": "t_welch",
              "statistic": tw, "df": dfw, "p_value": t_p(tw, dfw), "se": sew,
              "estimate_ci": [diff - tvw * sew, diff + tvw * sew], "cohen_d": dw,
              "effect_ci": d_ci(dw, n1, n2, conf) if dw else None,
              "df_method": "Welch-Satterthwaite"}
  return out

def rank_data(v):
  order = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
  while i < len(order):
    j = i
    while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]: j += 1
    avg = (i + j) / 2.0 + 1.0
    for k in range(i, j + 1): r[order[k]] = avg
    i = j + 1
  return r

def mannwhitney(x, y):
  n1, n2 = len(x), len(y)
  if n1 < 1 or n2 < 1: return {"valid": False, "reason": "空组"}
  allv = list(x) + list(y); r = rank_data(allv)
  U1 = sum(r[:n1]) - n1 * (n1 + 1) / 2.0; N = n1 + n2
  cnt = {}
  for v in allv: cnt[v] = cnt.get(v, 0) + 1
  tie = sum(c ** 3 - c for c in cnt.values())
  mu = n1 * n2 / 2.0
  var = n1 * n2 / 12.0 * ((N + 1) - tie / (N * (N - 1))) if N > 1 else 0.0
  m1 = quantile(sorted(x), 0.5); m2 = quantile(sorted(y), 0.5)
  out = {"valid": True, "method": "Mann-Whitney U test", "method_id": "mannwhitney", "n1": n1,
      "n2": n2, "U1": U1, "U2": n1 * n2 - U1, "median1": m1, "median2": m2,
      "rank_biserial": (2.0 * U1 / (n1 * n2)) - 1.0, "statistic": U1,
      "estimate_name": "median1 - median2", "estimate": m1 - m2}
  if var > 0:
    z = max(0.0, (abs(U1 - mu) - 0.5) / math.sqrt(var))
    out["z"] = z; out["p_value"] = norm_sf2(z)
    out["p_method"] = "normal approx, continuity + tie correction"
  return out

def anova(groups):
  k = len(groups); ni = [len(g) for g in groups]; N = sum(ni)
  if k < 2 or N - k <= 0: return {"valid": False, "reason": "组数或自由度不足"}
  means = [sum(g) / len(g) for g in groups]; grand = sum(sum(g) for g in groups) / N
  ssb = sum(n * (m - grand) ** 2 for n, m in zip(ni, means))
  ssw = sum(sum((x - m) ** 2 for x in g) for g, m in zip(groups, means))
  dfb, dfw = k - 1, N - k
  if ssw <= 0:
    return {"valid": False, "reason": "组内平方和为 0（全部组内零方差），F 无定义", "ssb": ssb, "ssw": ssw}
  msb, msw = ssb / dfb, ssw / dfw; F = msb / msw; sst = ssb + ssw
  return {"valid": True, "method": "one-way ANOVA", "method_id": "anova_oneway", "statistic": F,
      "df1": dfb, "df2": dfw, "p_value": f_sf(F, dfb, dfw), "ssb": ssb, "ssw": ssw, "sst": sst,
      "msb": msb, "msw": msw, "eta_squared": ssb / sst if sst else None,
      "omega_squared": (ssb - dfb * msw) / (sst + msw) if (sst + msw) else None,
      "grand_mean": grand, "group_means": means, "group_n": ni}

def kruskal(groups):
  k = len(groups)
  if k < 2: return {"valid": False, "reason": "组数 <2"}
  allv, tags = [], []
  for i, g in enumerate(groups):
    allv.extend(g); tags.extend([i] * len(g))
  N = len(allv)
  if N - k <= 0: return {"valid": False, "reason": "自由度不足"}
  r = rank_data(allv); Ri = [0.0] * k
  for rr, t in zip(r, tags): Ri[t] += rr
  ni = [len(g) for g in groups]
  H = 12.0 / (N * (N + 1)) * sum(ri * ri / n for ri, n in zip(Ri, ni)) - 3.0 * (N + 1)
  cnt = {}
  for v in allv: cnt[v] = cnt.get(v, 0) + 1
  tie = sum(c ** 3 - c for c in cnt.values())
  corr = 1.0 - tie / (N ** 3 - N) if N > 1 else 1.0
  Hc = H / corr if corr > 0 else H
  return {"valid": True, "method": "Kruskal-Wallis rank test", "method_id": "kruskal",
      "statistic": Hc, "statistic_uncorrected": H, "df": k - 1, "p_value": chi2_sf(Hc, k - 1),
      "epsilon_squared": max(0.0, (Hc - k + 1) / (N - k)) if N - k > 0 else None,
      "rank_means": [ri / n for ri, n in zip(Ri, ni)], "group_n": ni}

def hedges_g(x, y):
  n1, n2 = len(x), len(y)
  if n1 < 2 or n2 < 2: return None
  m1, m2 = sum(x) / n1, sum(y) / n2
  s1 = math.sqrt(sum((v - m1) ** 2 for v in x) / (n1 - 1))
  s2 = math.sqrt(sum((v - m2) ** 2 for v in y) / (n2 - 1))
  sp = math.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2))
  if sp == 0: return None
  d = (m1 - m2) / sp; J = 1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)
  ci = d_ci(d, n1, n2)
  return {"method": "Hedges g (bias-corrected SMD)", "cohen_d": d, "value": J * d, "J": J,
      "pooled_sd": sp, "ci": [J * ci[0], J * ci[1]] if ci else None,
      "ci_method": "Hedges-Olkin large-sample SE scaled by J (approximate)"}

def boot_ci(items, fn, B=2000, conf=0.95, label="boot"):
  """Percentile bootstrap CI; items are the resampling units (fixed seed)."""
  if not items: return None
  rnd = random.Random(zlib.crc32((label + _SALT).encode("utf-8")) & 0xFFFFFFFF)
  vals = []
  for _ in range(B):
    s = [items[rnd.randrange(len(items))] for _ in range(len(items))]
    try: v = fn(s)
    except Exception: v = None
    if isinstance(v, (int, float)) and v == v: vals.append(float(v))
  if len(vals) < max(20, B // 20): return None
  vals.sort()
  return [quantile(vals, (1 - conf) / 2), quantile(vals, 1 - (1 - conf) / 2)]

def adjust_p(pvals, method="holm"):
  idx = [i for i, p in enumerate(pvals) if p is not None]
  out = [None] * len(pvals); m = len(idx)
  if m == 0: return out
  if method == "bonferroni":
    for i in idx: out[i] = min(1.0, pvals[i] * m)
    return out
  order = sorted(idx, key=lambda i: pvals[i])
  if method == "bh":
    q = [0.0] * m
    for rank in range(m - 1, -1, -1):
      val = pvals[order[rank]] * m / (rank + 1)
      q[rank] = min(1.0, val if rank == m - 1 else min(val, q[rank + 1]))
    for rank, i in enumerate(order): out[i] = q[rank]
    return out
  prov = 0.0
  for rank, i in enumerate(order):
    prov = max(prov, (m - rank) * pvals[i]); out[i] = min(1.0, prov)
  return out

def correlate(x, y, conf=0.95):
  """Pearson r (+Fisher z CI), Spearman rho, and the bivariate OLS slope with CI."""
  n = min(len(x), len(y))
  if n < 3: return {"valid": False, "reason": "配对观测 <3"}
  mx, my = sum(x[:n]) / n, sum(y[:n]) / n
  sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
  sxx = sum((x[i] - mx) ** 2 for i in range(n)); syy = sum((y[i] - my) ** 2 for i in range(n))
  if sxx <= 0 or syy <= 0: return {"valid": False, "reason": "某变量零方差，r 无定义"}
  r = max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))
  def rp(v):
    if v is None or abs(v) >= 1: return None
    return t_p(v * math.sqrt((n - 2) / (1 - v * v)), n - 2)
  z = 1.959963984540054 if conf == 0.95 else norm_ppf((1 + conf) / 2)
  ci = None
  if abs(r) < 1 and n > 3:
    rr = 0.5 * math.log((1 + r) / (1 - r))
    ci = [math.tanh(rr - z / math.sqrt(n - 3)), math.tanh(rr + z / math.sqrt(n - 3))]
  rx, ry = rank_data(x[:n]), rank_data(y[:n])
  mrx, mry = sum(rx) / n, sum(ry) / n
  a = sum((rx[i] - mrx) * (ry[i] - mry) for i in range(n))
  b = sum((rx[i] - mrx) ** 2 for i in range(n)); c = sum((ry[i] - mry) ** 2 for i in range(n))
  rho = a / math.sqrt(b * c) if b > 0 and c > 0 else None
  slope = sxy / sxx
  resid = [(y[i] - my) - slope * (x[i] - mx) for i in range(n)]
  sse = sum(e * e for e in resid); df = n - 2
  se_slope = math.sqrt(sse / df / sxx) if df > 0 else None
  tv = t_ppf(1 - (1 - conf) / 2, df) if df > 0 else None
  return {"valid": True, "n": n, "pearson_r": r, "pearson_p": rp(r), "pearson_ci": ci,
      "spearman_rho": rho, "spearman_p": rp(rho), "r_squared": r * r,
      "slope": slope, "intercept": my - slope * mx,
      "slope_se": se_slope, "slope_df": df,
      "slope_p": t_p(slope / se_slope, df) if se_slope else None,
      "slope_ci": [slope - tv * se_slope, slope + tv * se_slope] if (se_slope and tv) else None,
      "method": "Pearson r with t(n-2); Spearman rho on average ranks; slope = Sxy/Sxx",
      "ci_method": "Fisher z transform (n>=4); slope CI via residual SE"}

MISS={"","na","n/a","nan","null","none","nil","-","--","\u2014","?","#n/a","#div/0!","\u7f3a\u5931","\u65e0","\u7a7a",".","..","n.a."}

def unit_of_name(n):
  m=re.search(r"[\uff08(]\s*([a-zA-Z\u00b5\u03bc%][a-zA-Z\u00b5\u03bc%/\\^0-9 ]{0,10})\s*[)\uff09]\s*$",n)
  if m: return m.group(1).strip()
  m=re.search(r"[_\s](cm|mm|kg|mg|ug|ml|ul|min|%|pa|kpa|mpa)$",n,re.I)
  return m.group(1) if m else None

def parse_num(s):
  """Return (value, unit_suffix); handles 1,234 / 12.5% / 12 mg / full-width digits."""
  if isinstance(s,(int,float)) and not isinstance(s,bool): return float(s),None
  t=str(s).strip().replace("\u3000"," ").replace("\uff0c",",").replace("\uff0e",".")
  t="".join(chr(ord(c)-0xFEE0) if "\uff10"<=c<="\uff19" else c for c in t)
  if not t: return None,None
  m=re.match(r"^([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)?(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(.*)$",t)
  if not m or m.group(1) in ("","+","-","."): return None,None
  try: return float(m.group(1).replace(",","")),(m.group(2).strip() or None)
  except Exception: return None,None

def profile(name,raw,dm):
  """Infer kind (numeric/categorical/empty), count missing, repair number formats."""
  c={"name":name,"n_cells":len(raw),"n_missing":0,"repaired":0,"ex":[],"mrow":[],
    "unit":dm.get("unit") or unit_of_name(name),"desc":dm.get("description")}
  nums,un,miss,nn=[],{},0,0
  for i,cell in enumerate(raw):
    if isinstance(cell,(int,float)) and not isinstance(cell,bool):
      nums.append(float(cell)); nn+=1; continue
    x=str(cell).strip()
    if x.lower() in MISS:
      nums.append(None); miss+=1; c["mrow"].append(i); continue
    if re.match(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}$",x): nums.append(x); continue
    v,u=parse_num(x)
    if v is not None and (u is None or len(u)<=12):
      if u:
        un[u]=un.get(u,0)+1
        if len(c["ex"])<5: c["ex"].append({"row":i+2,"raw":x,"value":v,"unit":u})
        c["repaired"]+=1
      nums.append(v); nn+=1
    else: nums.append(x)
  c["n_missing"]=miss; c["missing_rate"]=(miss/c["n_cells"]) if c["n_cells"] else None
  nm=c["n_cells"]-miss
  if nm==0: c.update({"kind":"empty","values":[None]*c["n_cells"]}); return c
  if nn>=0.95*nm:
    c["kind"]="numeric"; c["values"]=[v if isinstance(v,float) else None for v in nums]
    if un:
      c["unit_seen"]=un
      if c["unit"] is None: c["unit"]=sorted(un,key=lambda k:(-un[k],k))[0]
  else:
    uq={}
    for v in nums:
      if v is not None and not isinstance(v,float): uq[v]=uq.get(v,0)+1
    c.update({"kind":"categorical","levels":dict(sorted(uq.items(),key=lambda kv:(-kv[1],kv[0]))[:50]),
         "n_levels":len(uq),
         "values":[None if (v is None or isinstance(v,float)) else str(v) for v in nums]})
    if 2<=len(uq)<=15 and all(re.fullmatch(r"-?\d+(\.0+)?",v) for v in uq): c["numeric_coded"]=True
  return c
