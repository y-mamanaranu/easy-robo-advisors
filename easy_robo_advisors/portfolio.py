"""Portfolio."""
from collections import defaultdict
from pathlib import Path

import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from assets_checker.bitflyer import bitFlyerHandler
from assets_checker.monex import MonexHandler
from assets_checker.sbi import SBIHandler
from selenium.webdriver.chrome.options import Options


class Portfolio():
    """Analyze protfolio."""

    use_SBI = True

    use_Monex = True

    use_bitFlyer = True
    bitflyer_api_key = None
    bitflyer_api_secret = None

    income = 50000
    delay = 3
    tor = 0.2

    def update_accounts(self, options: Options = None):
        """Updaet accout information.

        Parameters
        ----------
        options : Options, optional
            Options for `webdriver`, by default None
        """
        options = options or Options()
        self.portfolio = defaultdict(lambda: dict(amount=0, valuation=0))

        if self.use_SBI:
            self._update_SBI(options)
        if self.use_Monex:
            self._update_Monex(options)
        if self.use_bitFlyer:
            self._update_bitFlyer(options)

        self.df_portfolio = pd.DataFrame(self.portfolio)
        self.df_portfolio = self.df_portfolio.transpose()
        self.df_portfolio = self.df_portfolio.rename_axis("ticker")
        self.df_portfolio = self.df_portfolio.reset_index()
        self.df_portfolio.ticker = self.df_portfolio.ticker.astype(str)

    def _update_SBI(self, options):
        self.SBI = SBIHandler(options=options)
        self.SBI.update()
        self.SBI.close()
        for _, row in self.SBI.df.iterrows():
            if row.valuation == 0:
                continue
            self.portfolio[row.ticker]["amount"] += row.amount
            self.portfolio[row.ticker]["valuation"] += row.valuation

    def _update_Monex(self, options):
        self.Monex = MonexHandler(options)
        self.Monex.update()
        self.Monex.close()
        for _, row in self.Monex.df.iterrows():
            if row.valuation == 0:
                continue
            self.portfolio[row.ticker]["amount"] += row.amount
            self.portfolio[row.ticker]["valuation"] += row.valuation

    def _update_bitFlyer(self, options):
        if not (self.bitflyer_api_key and self.bitflyer_api_secret):
            print("Need `self.bitflyer_api_key`"
                  " and `self.bitflyer_api_secret`.")
            print("Skip update bitFlyer.")
            return

        self.bitFlyer = bitFlyerHandler(options=options)
        self.bitFlyer.update(self.bitflyer_api_key, self.bitflyer_api_secret)
        self.bitFlyer.close()
        for i, row in self.bitFlyer.df.iterrows():
            if row.valuation == 0:
                continue
            self.portfolio[row.ticker]["amount"] += row.amount
            self.portfolio[row.ticker]["valuation"] += row.valuation

    def update_target_from_csv(self, path: Path):
        """Update target information from csv.

        Parameters
        ----------
        path : Path
            Path to csv
        """
        self.df_target = pd.read_csv(path)
        self.df_target = self.df_target.dropna(subset=['ticker'])
        self.df_target["ticker"] = self.df_target.ticker.astype(str)
        self.df_target = self.df_target.dropna(how='all', axis=1)

    @property
    def df(self):
        """Summarize all data."""
        try:
            return self.__df
        except AttributeError:
            self._upate_df()
            return self.__df

    def _upate_df(self):
        self.__df = pd.merge(self.df_portfolio, self.df_target, how="outer")
        self.__df.amount = self.__df.amount.replace(np.nan, 0)
        self.__df.valuation = self.__df.valuation.replace(np.nan, 0)
        self.__df.weight = self.__df.weight.apply(u.Quantity)
        self.__df["weight_float"] = self.__df.weight.astype(float)

        for i, row in self.__df.query("type != type").iterrows():
            print(f"Unknown `ticker` of `{row.ticker}` is detected.")

    def update_propose(self):
        """Generate propse from current and target portfolio."""
        self._update_per_month()
        self._update_per_day()
        self._update_per_dayn(20)

    @staticmethod
    def _curve_per_month(weight, valuation, total, income, delay, tor):
        total = (total + delay * income)
        weight = weight.astype(float)

        final = weight * total
        per_month = (final - valuation) / delay

        tor_month = total * tor * weight / (1 + tor * weight) / delay
        filter = np.abs(per_month) <= tor_month
        for i, item in filter.iteritems():
            if item is True:
                per_month.iloc[i] = 0
            else:
                diff = np.sign(per_month.iloc[i]) * tor_month.iloc[i]
                per_month.iloc[i] -= diff

        return per_month * income / per_month.sum()

    def _update_per_month(self):
        total = self.df["valuation"].sum()

        self.df["per_month"] = self._curve_per_month(
            self.df.weight,
            self.df.valuation,
            total,
            self.income,
            self.delay,
            self.tor
        )

        filter = self.df.currency == self.df.currency
        currency_to_prepare = np.unique(self.df.currency[filter].values)
        for c in currency_to_prepare:
            diff = self.df.per_month[self.df.currency == c].sum()
            self.df.loc[self.df.ticker == c, "per_month"] += diff

        val = self.df.per_month * self.df.amount / self.df.valuation
        self.df["per_month_amount"] = val

        filter = (self.df.per_month == self.df.per_month)
        self.df.loc[filter, 'per_month'] = self.df[filter].per_month.apply(int)

        val = self.df.per_month_amount
        filter = (self.df.dtype == "int") & (val == val)
        val = self.df[filter].per_month_amount.apply(int)
        self.df.loc[filter, 'per_month_amount'] = val

    def _update_per_day(self):
        self.df["per_day"] = self.df.per_month / 30
        self.df["per_day_amount"] = self.df.per_month_amount / 30

        filter = (self.df.per_day == self.df.per_day)
        self.df.loc[filter, 'per_day'] = self.df[filter].per_day.apply(int)

        val = self.df.per_day_amount
        filter = (self.df.dtype == "int") & (val == val)
        val = self.df[filter].per_day_amount.apply(int)
        self.df.loc[filter, 'per_day_amount'] = val

    def _update_per_dayn(self, n):
        self.df[f"per_day{n}"] = self.df.per_month / 20
        self.df[f"per_day{n}_amount"] = self.df.per_month_amount / 20

        filter = (self.df[f"per_day{n}"] == self.df[f"per_day{n}"])
        val = self.df[filter][f"per_day{n}"].apply(int)
        self.df.loc[filter, f"per_day{n}"] = val

        val = self.df[f"per_day{n}_amount"]
        filter = (self.df.dtype == "int") & (val == val)
        val = self.df[filter][f"per_day{n}_amount"].apply(int)
        self.df.loc[filter, f"per_day{n}_amount"] = val

    @property
    def _propose_columns(self):
        return ["ticker",
                "amount",
                "valuation",
                "per_month",
                "per_month_amount",
                "per_day",
                "per_day_amount",
                "per_day20",
                "per_day20_amount"]

    def propose(self, account):
        """Summarize propose."""
        return self.df[self.df.account == account][self._propose_columns]

    @property
    def proposable(self):
        """List of account."""
        return np.unique(self.df.account.values)

    @property
    def _type_detail(self):
        return {
            "Stock": [
                "Developed Stock",
                "Emerging Stock",
                "Real Estate",
                "Corporate Bonds"
            ],
            "Bonds": [
                "Cache",
                "Government Bonds"
            ],
            "Commodity": [
                "Energy",
                "Precious Metal",
                "Industrial Metal",
                "Agriculture",
                "Crypto"
            ]
        }

    def plot(self, ax, value, title=None):
        """Plot data."""
        vals = self.df[value]

        iner_labels = list(self._type_detail.keys())
        iner_vals = np.array([vals[self.df.type == label].sum()
                             for label in iner_labels])
        iner_labels_per = [
            f"{label}\n{val:1.1f}%" for label,
            val in zip(iner_labels, 100 * iner_vals / iner_vals.sum())]

        outer_labels = [detail
                        for label in iner_labels
                        for detail in self._type_detail[label]]
        outer_vals = np.array([vals[self.df.detail == detail].sum()
                              for detail in outer_labels])
        outer_labels_per = [
            f"{label} {val:1.1f}%"
            for label, val in zip(
                outer_labels,
                100 * outer_vals / outer_vals.sum())]

        def color(cmap, i, arr):
            if len(arr) < 4:
                return cmap(4 * i + 1 + np.arange(len(arr)))
            else:
                rarr = np.linspace(0, 1, len(arr), endpoint=True)
                c0 = np.array(cmap(4 * i + 1))
                c1 = np.array(cmap(4 * i + 3))
                return [c0 * r + c1 * (1 - r) for r in rarr]

        cmap = plt.get_cmap("tab20c")
        iner_colors = cmap(np.arange(len(iner_labels)) * 4)
        outer_colors = [c
                        for i, label in enumerate(iner_labels)
                        for c in color(cmap, i, self._type_detail[label])]

        outer_donut = ax.pie(
            outer_vals,
            radius=1.2,
            wedgeprops=dict(width=0.2, edgecolor='w'),
            startangle=90,
            counterclock=False,
            colors=outer_colors,
            pctdistance=0.85)

        ax.pie(iner_vals,
               labels=iner_labels_per,
               radius=1,
               wedgeprops=dict(edgecolor='w'),
               startangle=90,
               counterclock=False,
               colors=iner_colors,
               labeldistance=0.6,
               textprops={"horizontalalignment": "center",
                          "color": "w",
                          "weight": "bold"})

        wedges, _ = outer_donut
        kw = dict(arrowprops=dict(arrowstyle="-"), zorder=0, va="center")
        for i, p in enumerate(wedges):
            if outer_vals[i] == 0:
                continue

            ang = (p.theta2 - p.theta1) / 2. + p.theta1
            y = 1.2 * np.sin(np.deg2rad(ang))
            x = 1.2 * np.cos(np.deg2rad(ang))
            y_text = 1.4 * np.sin(np.deg2rad(ang))
            x_text = 1.4 * np.sign(np.cos(np.deg2rad(ang)))

            horizontalalignment = {-1: "right", 1: "left"}[int(np.sign(x))]
            connectionstyle = f"angle,angleA=0,angleB={ang}"
            kw["arrowprops"].update({"connectionstyle": connectionstyle})

            ax.annotate(outer_labels_per[i],
                        xy=(x, y),
                        xytext=(x_text, y_text),
                        horizontalalignment=horizontalalignment,
                        **kw)

        ax.set_title(title)
