// Simple demo: a + b + c = 0
// Observe a with noise; prior on b is a mixture of Gaussians; prior on c is Gaussian.
// Inference recovers the joint posterior over (b, c).

data {
  int<lower=1> n_obs;          // number of observations
  array[n_obs] real a_obs;     // observed values of a (= -(b+c) + noise)
  real<lower=0> sigma_obs;     // observation noise std

  // Prior on b: mixture of K Gaussians
  int<lower=1> K;
  vector[K] b_mix_mu;
  vector<lower=0>[K] b_mix_sigma;
  simplex[K] b_mix_weights;

  // Prior on c: single Gaussian
  real c_mu;
  real<lower=0> c_sigma;
}

parameters {
  real b;
  real c;
}

model {
  // Prior on c
  c ~ normal(c_mu, c_sigma);

  // Prior on b: mixture of Gaussians via log_mix
  {
    vector[K] lps;
    for (k in 1:K)
      lps[k] = log(b_mix_weights[k]) + normal_lpdf(b | b_mix_mu[k], b_mix_sigma[k]);
    target += log_sum_exp(lps);
  }

  // Likelihood: each observation of a satisfies a = -(b+c) + noise
  // => a_obs ~ normal(-(b+c), sigma_obs)
  for (i in 1:n_obs)
    a_obs[i] ~ normal(-(b + c), sigma_obs);
}
