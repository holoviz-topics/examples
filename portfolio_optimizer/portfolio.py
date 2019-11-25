#!/usr/bin/env python
# coding: utf-8

from io import BytesIO

import numpy as np
import numba as nb
import pandas as pd
import holoviews as hv
import panel as pn

from scipy.optimize import minimize

hv.extension('bokeh')

@nb.jit
def random_allocation(stocks, shifted, num_ports=15000):
    log_ret = np.log(stocks/shifted)
    
    _, ncols = stocks.shape

    all_weights = np.zeros((num_ports, ncols))
    ret_arr = np.zeros(num_ports)
    vol_arr = np.zeros(num_ports)
    sharpe_arr = np.zeros(num_ports)
    
    for ind in range(num_ports):

        # Create Random Weights
        weights = np.random.random(ncols)

        # Rebalance Weights
        weights = weights / np.sum(weights)

        # Save Weights
        all_weights[ind,:] = weights

        # Expected Return
        mean_ret = np.array([np.nanmean(log_ret[:, i]) for i in range(ncols)])
        ret_arr[ind] = np.sum((mean_ret * weights) * 252)

        # Expected Variance
        vol_arr[ind] = np.sqrt(np.dot(weights, np.dot(np.cov(log_ret[1:], rowvar=False) * 252, weights)))

        # Sharpe Ratio
        sharpe_arr[ind] = ret_arr[ind]/vol_arr[ind]
    return all_weights, ret_arr, vol_arr, sharpe_arr


def find_minimal_volatility(possible_return):
    # 0-1 bounds for each weight
    cols = len(stocks.columns)
    bounds = tuple((0, 1) for i in range(cols))
    # Initial Guess (equal distribution)
    init_guess = [1./cols for i in range(cols)]
    cons = ({'type':'eq','fun': check_sum},
            {'type':'eq','fun': lambda w: get_ret_vol_sr(w)[0] - possible_return})
    return minimize(minimize_volatility, init_guess, method='SLSQP', bounds=bounds, constraints=cons)


def allocation(ind, vol_arr, ret_arr, all_weights, stocks):
    return pd.DataFrame(zip(stocks.columns, all_weights[ind]), columns=['Stock', 'Weight'])


text = """
#  Portfolio optimization

This application performs portfolio optimization given a set of stock time series.

To optimize your portfolio:

1. Upload a CSV of the daily stock time series for the stocks you are considering
2. Select the stocks to be included.
3. Run the Analysis
4. Click on the Return/Volatility plot to select the desired risk/reward profile
"""

file_input = pn.widgets.FileInput(align='center')
selector = pn.widgets.MultiSelect(name='Select stocks')
n_samples = pn.widgets.IntSlider(name='Random samples', value=5000, start=1000, end=10000, step=1000)
button = pn.widgets.Button(name='Run Analysis')

widgets = pn.WidgetBox(
    pn.panel(text, margin=(0, 10)),
    pn.panel('Upload a CSV containing stock data:', margin=(0, 10)),
    file_input,
    selector,
    n_samples,
    button
)

# Contraints
def check_sum(weights):
    '''
    Returns 0 if sum of weights is 1.0
    '''
    return np.sum(weights) - 1

def plot_portfolios(ds):
    return hv.Scatter(ds, 'Volatility', ['Return', 'Sharpe Ratio']).opts(
        color='Sharpe Ratio', cmap='plasma', padding=0.1, responsive=True, height=500, colorbar=True,
        clabel='Sharpe Ratio', toolbar='above')

def plot_max_sharpe(ds):
    vol_arr, ret_arr, sharpe_arr = ds['Volatility'], ds['Return'], ds['Sharpe Ratio']
    ind = sharpe_arr.argmax()
    max_sr_ret = ret_arr[ind]
    max_sr_vol = vol_arr[ind]
    return hv.Scatter([(max_sr_vol, max_sr_ret)], 'Volatility', 'Return', label='Max Sharpe Ratio').opts(
        size=10, line_color='black', tools=['hover'])

def get_stocks():
    if file_input.value is None:
        stock_file = 'stocks.csv'
    else:
        stock_file = BytesIO()
        stock_file.write(file_input.value)
        stock_file.seek(0)
    return pd.read_csv(stock_file, index_col='Date', parse_dates=True)

def update_stocks(event):
    stocks = list(get_stocks().columns)
    selector.set_param(options=stocks, value=stocks)

file_input.param.watch(update_stocks, 'value')
update_stocks(None)

@pn.depends(button.param.clicks)
def get_portfolio_analysis(_):
    stocks = get_stocks()
    stocks = stocks[selector.value]
    log_ret = np.log(stocks/stocks.shift(1))
    log_ret_array = log_ret.values

    @nb.jit
    def get_ret_vol_sr(weights):
        """
        Takes in weights, returns array of return, volatility, sharpe ratio
        """
        (ncols,) = weights.shape
        mean_ret = np.array([np.nanmean(log_ret_array[:, i]) for i in range(ncols)])
        ret = np.sum(mean_ret * weights) * 252
        
        log_ret[log_ret>0] = 0
        vol = np.sqrt(np.dot(weights.T, np.dot(np.cov(log_ret_array[1:], rowvar=False) * 252, weights)))
        sr = ret/vol
        
        return np.array([ret,vol,sr])
    

    def minimize_volatility(weights):
        return get_ret_vol_sr(weights)[1]

    def minimize_difference(weights, des_vol, des_ret):
        ret, vol, _ = get_ret_vol_sr(weights)
        return abs(des_ret - ret) + abs(des_vol-vol)

    def find_best_allocation(vol, ret):
        cols = len(stocks.columns)
        bounds = tuple((0, 1) for i in range(cols))
        init_guess = [1./cols for i in range(cols)]
        cons = ({'type':'eq','fun': check_sum},
                {'type':'eq','fun': lambda w: get_ret_vol_sr(w)[0] - ret},
                {'type':'eq','fun': lambda w: get_ret_vol_sr(w)[1] - vol})
        return minimize(minimize_difference, init_guess, args=(vol, ret),
                        method='SLSQP', bounds=bounds, constraints=cons)
    
    def random_allocation_cb(n_samples):
        all_weights, ret_arr, vol_arr, sharpe_arr = random_allocation(
            stocks.values, stocks.shift(1).values, num_ports=n_samples)
        vdims = [*('%s Weight' % c for c in stocks.columns), 'Return', 'Volatility', 'Sharpe Ratio']
        return hv.Dataset((*all_weights.T,  ret_arr, vol_arr, sharpe_arr), vdims=vdims)

    def compute_frontier(start=0, end=0.3, n=100):
        frontier_ret = np.linspace(start, end, n)
        frontier_volatility = []

        cols = len(stocks.columns)
        bounds = tuple((0, 1) for i in range(cols))
        # Initial Guess (equal distribution)
        init_guess = [1./cols for i in range(cols)]
        for possible_return in frontier_ret:
            # function for return
            cons = ({'type':'eq','fun': check_sum},
                    {'type':'eq','fun': lambda w: get_ret_vol_sr(w)[0] - possible_return})

            result = minimize(minimize_volatility,init_guess,method='SLSQP',bounds=bounds,constraints=cons)
            frontier_volatility.append(result['fun'])
        return frontier_volatility, frontier_ret
    
    def plot_frontier(ds):
        ret_min, ret_max = ds.range('Return')
        ret_pad = (ret_max - ret_min) * 0.1
        frontier = compute_frontier(ret_min-ret_pad, ret_max+ret_pad, 100)
        return hv.Curve(frontier, label='Efficient Frontier').opts(
            line_dash='dashed', color='green')

    def plot_closest(x, y):
        vdims = list(stocks.columns)
        if (x is None or y is None):
            return hv.Points([], vdims=vdims)

        opt = find_best_allocation(x, y)
        weights = opt.x
        ret, vol, _ = get_ret_vol_sr(weights)
        return hv.Points([(vol, ret, *weights)], ['Volatility', 'Return'], vdims=vdims, label='Current Portfolio').opts(
            color='green', size=10, line_color='black', tools=['hover'])
    
    def plot_table(ds):
        arr = ds.array()
        weights = list(zip(stocks.columns, arr[0, 2:])) if len(arr) else []
        return hv.Table(weights, 'Stock', 'Weight').opts(editable=True)
    
    def portfolio_text(ds):
        arr = ds.array()
        ret, vol, sharpe = get_ret_vol_sr(arr[0, 2:])
        text = """
        The selected portfolio has a volatility of %.2f, a return of %.2f
        and Sharpe ratio of %.2f.
        """ % (vol, ret, sharpe)
        return hv.Div(text).opts(height=40)

    weights = np.array([1./len(selector.value) for _ in selector.value])
    ret, vol, _ = get_ret_vol_sr(weights)
    
    posxy = hv.streams.Tap(y=ret, x=vol)

    closest = hv.DynamicMap(plot_closest, streams=[posxy])
    table = closest.apply(plot_table)

    random = random_allocation_cb(n_samples.value)
    vol_ret = (random.apply(plot_portfolios) * random.apply(plot_frontier) * random.apply(plot_max_sharpe) * closest).opts(
        legend_position='bottom_right')
    div = closest.apply(portfolio_text)
    
    start, end = stocks.index.min(), stocks.index.max()
    year = pn.widgets.DateRangeSlider(name='Year', value=(start, end), start=start, end=end)
    investment = pn.widgets.Spinner(name='Investment Value in $', value=5000, step=1000, start=1000, end=100000)
    
    investment_widgets = pn.Row(year, investment)
    
    def plot_return_curve(table, investment, dates):
        weight = table['Weight']
        allocations = weight * investment
        amount = allocations/stocks[dates[0]:].iloc[0]
        return hv.Curve((stocks[dates[0]:dates[1]] * amount).sum(axis=1).reset_index().rename(columns={0: 'Total Value ($)'})).opts(
            responsive=True, framewise=True, min_height=300, padding=(0.05, 0.1))
    
    return_curve = table.apply(plot_return_curve, investment=investment.param.value, dates=year.param.value)
    
    reindexed = stocks.reset_index()
    timeseries = hv.NdOverlay({col: hv.Curve(reindexed, 'Date', col).redim(**{col: 'Stock Price ($)'}) for col in stocks.columns}).opts(
        title_format='Daily Stock Price', min_height=300, responsive=True, show_grid=True, legend_position='top_left')
    
    log_ret_ds = hv.Dataset(log_ret) 
    log_ret_hists = hv.NdLayout({col: log_ret_ds.hist(col, num_bins=100, adjoin=False) for col in log_ret.columns}, kdims=['Stock']).cols(2).opts(
        hv.opts.NdLayout(sizing_mode='stretch_width'), hv.opts.Histogram(height=300, min_width=400, responsive=True))
    
    return pn.Tabs(
            ('Analysis', pn.Column(
                pn.Row(vol_ret, pn.layout.Spacer(width=20), pn.Column(div, table), sizing_mode='stretch_width'),
                pn.Column(pn.Row(year, investment), return_curve, sizing_mode='stretch_width'),
                sizing_mode='stretch_width')),
            ('Timeseries', timeseries),
            ('Log Return', pn.Column(
                '## Daily normalized log returns',
                'Width of distribution indicates volatility and center of distribution the mean daily return.',
                log_ret_hists,
                sizing_mode='stretch_width'
            ))
        )

explanation = """
The code for this app was taken from [this excellent introduction to Python for Finance](https://github.com/PrateekKumarSingh/Python/tree/master/Python%20for%20Finance/Python-for-Finance-Repo-master).
To learn some of the background and theory about portfolio optimization see [this notebook](https://github.com/PrateekKumarSingh/Python/blob/master/Python%20for%20Finance/Python-for-Finance-Repo-master/09-Python-Finance-Fundamentals/02-Portfolio-Optimization.ipynb). 
"""

pn.Row(pn.Column(widgets, explanation), pn.layout.Spacer(width=20), get_portfolio_analysis).servable()
