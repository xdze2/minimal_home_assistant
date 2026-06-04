// Simple demo: a + b + c = 0
// All three are parameters with priors.
// The model is: y = a + b + c = 0 (observed as soft constraint with noise sigma_y).

data {
  // Prior on a: single Gaussian
  real a_mu;
  real<lower=0> a_sigma;

  // Prior on b: mixture of K Gaussians
  int<lower=1> K;
  vector[K] b_mix_mu;
  vector<lower=0>[K] b_mix_sigma;
  simplex[K] b_mix_weights;

  // Prior on c: single Gaussian
  real c_mu;
  real<lower=0> c_sigma;

  // Observation noise for the constraint y = a+b+c ~ 0
  real<lower=0> sigma_y;
}

parameters {
  real a;
  real b;
  real c;
}

model {
  // Priors
  a ~ normal(a_mu, a_sigma);
  c ~ normal(c_mu, c_sigma);

  // Prior on b: mixture of Gaussians via log_mix
  {
    vector[K] lps;
    for (k in 1:K)
      lps[k] = log(b_mix_weights[k]) + normal_lpdf(b | b_mix_mu[k], b_mix_sigma[k]);
    target += log_sum_exp(lps);
  }

  // Likelihood: observe y = 0 = a + b + c (soft constraint)
  0 ~ normal(a + b + c, sigma_y);
}
