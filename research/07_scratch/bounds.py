"""One-sided 95% upper bounds (Clopper-Pearson) on the wrong-claim rate after an audit."""
from math import comb
def cdf(k,n,p): return sum(comb(n,i)*p**i*(1-p)**(n-i) for i in range(k+1))
def upper(k,n,alpha=0.05):
    lo,hi=0.0,1.0
    for _ in range(60):
        m=(lo+hi)/2
        if cdf(k,n,m)>alpha: lo=m
        else: hi=m
    return hi
for n in (100,200,300,460,600,800,1000,1500):
    print(n, " ".join(f"k={k}:{upper(k,n):.2%}" for k in range(0,5)))
# smallest n that proves <=1% and <=0.5% with k errors
for target in (0.01,0.005,0.02):
    out=[]
    for k in range(0,4):
        n=k+1
        while upper(k,n)>target: n+=1
        out.append(f"k={k}: n>={n}")
    print("target",target, out)
