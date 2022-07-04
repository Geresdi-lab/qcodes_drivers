import warnings
import logging
import numpy as np
import time
import scipy.optimize as spopt
from scipy.constants import hbar
from scipy.interpolate import splrep, splev
from scipy.ndimage.filters import gaussian_filter1d


from resonator_tools.utilities import plotting, save_load, Watt2dBm, dBm2Watt
from resonator_tools.circlefit import circlefit
from resonator_tools.calibration import calibration

##
## z_data_raw denotes the raw data
## z_data denotes the normalized data
##		  

class reflection_port(circlefit, save_load, plotting, calibration):
    '''
    normal direct port probed in reflection
    '''
    def __init__(self, f_data=None, z_data_raw=None):
        self.porttype = 'direct'
        self.fitresults = {}
        self.z_data = None
        if f_data is not None:
            self.f_data = np.array(f_data)
        else:
            self.f_data=None
        if z_data_raw is not None:
            self.z_data_raw = np.array(z_data_raw)
        else:
            self.z_data=None
        self.phasefitsmooth = 3

    def _S11(self,f,fr,k_c,k_i):
        '''
        use either frequency or angular frequency units
        for all quantities
        k_l=k_c+k_i: total (loaded) coupling rate
        k_c: coupling rate
        k_i: internal loss rate
        '''
        return ((k_c-k_i)+2j*(f-fr))/((k_c+k_i)-2j*(f-fr))

    def get_delay(self,f_data,z_data,delay=None,ignoreslope=True,guess=True):
        '''
        ignoreslope option not used here
        retrieves the cable delay assuming the ideal resonance has a circular shape
        modifies the cable delay until the shape Im(S21) vs Re(S21) is circular
        see "do_calibration"
        '''
        maxval = np.max(np.absolute(z_data))
        z_data = z_data/maxval
        A1, A2, A3, A4, fr, Ql = self._fit_skewed_lorentzian(f_data,z_data)
    
        #print(A1, A2, A3, A4, fr, Ql)
        if self.df_error/fr > 0.0001 or self.dQl_error/Ql>0.1:
            print("WARNING: Calibration using Lorentz fit failed, trying phase fit...")
            A1 = np.mean(np.absolute(z_data))
            A2 = 0.
            A3 = 0.
            A4 = 0.
            #fr = np.mean(f_data)
            f = splrep(f_data,np.unwrap(np.angle(z_data)),k=5,s=self.phasefitsmooth)
            fr = f_data[np.argmax(np.absolute(splev(f_data,f,der=1)))]
            Ql = 1e4
        if ignoreslope==True:
            A2 = 0.
        else:
            A2 = 0.
            print("WARNING: The ignoreslope option is ignored! Corrections to the baseline should be done manually prior to fitting.")
            print("see also: resonator_tools.calibration.fit_baseline_amp() etc. for help on fitting the baseline.")
            print("There is also an example ipython notebook for using this function.")
            print("However, make sure to understand the impact of the baseline (parasitic coupled resonances etc.) on your system.")
            #z_data = (np.absolute(z_data)-A2*(f_data-fr)) * np.exp(np.angle(z_data)*1j)  #usually not necessary
        if delay is None:
            if guess==True:
                delay = self._guess_delay(f_data,z_data)
            else:
                delay=0.
            delay = self._fit_delay(f_data,z_data,delay,maxiter=800)
        params = [A1, A2, A3, A4, fr, Ql]
        return delay, params 

#     def do_calibration(self,f_data,z_data,ignoreslope=True,guessdelay=True,fixed_delay=None):
#         '''
#         calculating parameters for normalization
#         '''
#         delay, params = self.get_delay(f_data,z_data,ignoreslope=ignoreslope,guess=guessdelay,delay=fixed_delay)
#         z_data = (z_data-params[1]*(f_data-params[4]))*np.exp(2.*1j*np.pi*delay*f_data)
#         xc, yc, r0 = self._fit_circle(z_data)
#         zc = np.complex(xc,yc)
        
#         fitparams = self._phase_fit(f_data,self._center(z_data,zc),0.,np.absolute(params[5]),params[4])
#         theta, Ql, fr = fitparams
#         beta = self._periodic_boundary(theta+np.pi,np.pi) ###

#         offrespoint = np.complex((xc+r0*np.cos(beta)),(yc+r0*np.sin(beta)))
#         alpha = self._periodic_boundary(np.angle(offrespoint)+np.pi,np.pi)
#         #print(f"alpha = {alpha}")
#         #a = np.absolute(offrespoint)
#         #alpha = np.angle(zc)
#         a = r0 + np.absolute(zc)
#         return delay, a, alpha, fr, Ql, params[1], params[4]

    def do_calibration(self,f_data,z_data, fixed_delay = None, ignoreslope=True, guesses=None):
        '''
        calculating parameters for normalization
        '''
        #delay, params = self.get_delay(f_data,z_data,ignoreslope=ignoreslope,guess=guessdelay,delay=fixed_delay)
        delay, params = self.manual_fit_phase(f_data,z_data, delay=fixed_delay, ignoreslope=ignoreslope, guesses=None)
        z_data = (z_data-params[1]*(f_data-params[4]))*np.exp(2.*1j*np.pi*delay*f_data)
        xc, yc, r0 = self._fit_circle(z_data)
        zc = np.complex(xc,yc)
        
        fitparams = self._phase_fit(f_data,self._center(z_data,zc),0.,np.absolute(params[5]),params[4])
        theta, Ql, fr = fitparams
        beta = self._periodic_boundary(theta+np.pi,np.pi) ###

        offrespoint = np.complex((xc+r0*np.cos(beta)),(yc+r0*np.sin(beta)))
        alpha = self._periodic_boundary(np.angle(offrespoint)+np.pi,np.pi)
        #print(f"alpha = {alpha}")
        #a = np.absolute(offrespoint)
        #alpha = np.angle(zc)
        a = r0 + np.absolute(zc)
        #print(f"do calbiration: r0 = {self.r0}, zc = {zc}")
        return delay, a, alpha, fr, Ql, params[1], params[4]
               


    def do_normalization(self,f_data,z_data,delay,amp_norm,alpha,A2,frcal):
        '''
        transforming resonator into canonical position
        '''
        #print(-A2*(f_data-frcal))
        return (z_data-A2*(f_data-frcal))/amp_norm*np.exp(1j*(-alpha+2.*np.pi*delay*f_data))
    
        
    def circlefit(self,f_data,z_data,fr=None,Ql=None,refine_results=False,calc_errors=True):
        '''
        S11 version of the circlefit
        '''

        if fr is None: fr=f_data[np.argmin(np.absolute(z_data))]
        if Ql is None: Ql=1e6
        xc, yc, r0 = self._fit_circle(z_data,refine_results=refine_results)
        phi0 = -np.arcsin(yc/r0)
        self.phi = phi0
        
        theta0 = self._periodic_boundary(phi0+np.pi,np.pi)
        z_data_corr = self._center(z_data,np.complex(xc,yc))
        theta0, Ql, fr = self._phase_fit(f_data,z_data_corr,theta0,Ql,fr)
        #print("Ql from phasefit is: " + str(Ql))
        Qi = Ql/(1.-r0)
        Qc = 1./(1./Ql-1./Qi)

        results = {"Qi":Qi,"Qc":Qc,"Ql":Ql,"fr":fr,"theta0":theta0}

        #calculation of the error
        p = [fr,Qc,Ql]
        #chi_square, errors = rt.get_errors(rt.residuals_notch_ideal,f_data,z_data,p)
        if calc_errors==True:
            chi_square, cov = self._get_cov_fast_directrefl(f_data,z_data,p)
            #chi_square, cov = rt.get_cov(rt.residuals_notch_ideal,f_data,z_data,p)

            if cov is not None:
                errors = np.sqrt(np.diagonal(cov))
                fr_err,Qc_err,Ql_err = errors
                #calc Qi with error prop (sum the squares of the variances and covariaces)
                dQl = 1./((1./Ql-1./Qc)**2*Ql**2)
                dQc = - 1./((1./Ql-1./Qc)**2*Qc**2)
                Qi_err = np.sqrt((dQl**2*cov[2][2]) + (dQc**2*cov[1][1])+(2*dQl*dQc*cov[2][1]))	 #with correlations
                errors = {"Ql_err":Ql_err, "Qc_err":Qc_err, "fr_err":fr_err,"chi_square":chi_square,"Qi_err":Qi_err}
                results.update( errors )
            else:
                print("WARNING: Error calculation failed!")
        else:
            #just calc chisquared:
            fun2 = lambda x: self._residuals_notch_ideal(x,f_data,z_data)**2
            chi_square = 1./float(len(f_data)-len(p)) * (fun2(p)).sum()
            errors = {"chi_square":chi_square}
            results.update(errors)

        return results

    
    def autofit(self,electric_delay=None,fcrop=None, manual_calibrate = True):
        '''
        automatic calibration and fitting
        electric_delay: set the electric delay manually
        fcrop = (f1,f2) : crop the frequency range used for fitting
        '''
        if fcrop is None:
            self._fid = np.ones(self.f_data.size,dtype=bool)
        else:
            f1, f2 = fcrop
            self._fid = np.logical_and(self.f_data>=f1,self.f_data<=f2)
            
        if manual_calibrate:
            delay, amp_norm, alpha, fr, Ql, A2, frcal =\
            self._manual_calibrate(self.f_data[self._fid],self.z_data_raw[self._fid],ignoreslope=True,guessdelay=False,fixed_delay=electric_delay)
            #print(delay, amp_norm, alpha, fr, Ql, A2,)
        else:
            delay, amp_norm, alpha, fr, Ql, A2, frcal =\
            self.do_calibration(self.f_data[self._fid],self.z_data_raw[self._fid],fixed_delay=electric_delay, ignoreslope = True, guesses = None)

        self.z_data = self.do_normalization(self.f_data,self.z_data_raw,delay,amp_norm,alpha,A2,frcal)
        self.fitresults = self.circlefit(self.f_data[self._fid],self.z_data[self._fid],fr,Ql,refine_results=True,calc_errors=True)
        
        self.z_data_sim = A2*(self.f_data-frcal)+self._S11_directrefl(self.f_data,fr=self.fitresults["fr"],Ql=self.fitresults["Ql"],Qc=self.fitresults["Qc"],a=-amp_norm,alpha=alpha,delay=delay)
        #print(f"amp = {amp_norm}")
        self.z_data_sim_norm = self._S11_directrefl(self.f_data,fr=self.fitresults["fr"],Ql=self.fitresults["Ql"],Qc=self.fitresults["Qc"],a=1.,alpha=0.,delay=0.)		
        self._delay = delay
        
    def GUIfit(self):
        '''
        automatic fit with possible user interaction to crop the data and modify the electric delay
        f1,f2,delay are determined in the GUI. Then, data is cropped and autofit with delay is performed
        '''
        #copy data
        fmin, fmax = self.f_data.min(), self.f_data.max()
        self.autofit()
        self.__delay = self._delay
        #prepare plot and slider
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Slider, Button
        fig, ((ax2,ax0),(ax1,ax3)) = plt.subplots(nrows=2,ncols=2)
        plt.suptitle('Normalized data. Use the silders to improve the fitting if necessary.')
        plt.subplots_adjust(left=0.25, bottom=0.25)
        l0, = ax0.plot(self.f_data*1e-9,np.absolute(self.z_data))
        l1, = ax1.plot(self.f_data*1e-9,np.angle(self.z_data))
        l2, = ax2.plot(np.real(self.z_data),np.imag(self.z_data))
        l0s, = ax0.plot(self.f_data*1e-9,np.absolute(self.z_data_sim_norm))
        l1s, = ax1.plot(self.f_data*1e-9,np.angle(self.z_data_sim_norm))
        l2s, = ax2.plot(np.real(self.z_data_sim_norm),np.imag(self.z_data_sim_norm))
        ax0.set_xlabel('f (GHz)')
        ax1.set_xlabel('f (GHz)')
        ax2.set_xlabel('real')
        ax0.set_ylabel('amp')
        ax1.set_ylabel('phase (rad)')
        ax2.set_ylabel('imagl')
        fr_ann = ax3.annotate('fr = %e Hz +- %e Hz' % (self.fitresults['fr'],self.fitresults['fr_err']),xy=(0.1, 0.8), xycoords='axes fraction')
        Ql_ann = ax3.annotate('Ql = %e +- %e' % (self.fitresults['Ql'],self.fitresults['Ql_err']),xy=(0.1, 0.6), xycoords='axes fraction')
        Qc_ann = ax3.annotate('Qc = %e +- %e' % (self.fitresults['Qc'],self.fitresults['Qc_err']),xy=(0.1, 0.4), xycoords='axes fraction')
        Qi_ann = ax3.annotate('Qi = %e +- %e' % (self.fitresults['Qi'],self.fitresults['Qi_err']),xy=(0.1, 0.2), xycoords='axes fraction')
        axcolor = 'lightgoldenrodyellow'
        axdelay = plt.axes([0.25, 0.05, 0.65, 0.03], facecolor=axcolor)
        axf2 = plt.axes([0.25, 0.1, 0.65, 0.03], facecolor=axcolor)
        axf1 = plt.axes([0.25, 0.15, 0.65, 0.03], facecolor=axcolor)
        sscale = 10.
        sdelay = Slider(axdelay, 'delay', -1., 1., valinit=self.__delay/(sscale*self.__delay),valfmt='%f')
        df = (fmax-fmin)*0.05
        sf2 = Slider(axf2, 'f2', (fmin-df)*1e-9, (fmax+df)*1e-9, valinit=fmax*1e-9,valfmt='%.10f GHz')
        sf1 = Slider(axf1, 'f1', (fmin-df)*1e-9, (fmax+df)*1e-9, valinit=fmin*1e-9,valfmt='%.10f GHz')
        def update(val):
            self.autofit(electric_delay=sdelay.val*sscale*self.__delay,fcrop=(sf1.val*1e9,sf2.val*1e9))
            l0.set_data(self.f_data*1e-9,np.absolute(self.z_data))
            l1.set_data(self.f_data*1e-9,np.angle(self.z_data))
            l2.set_data(np.real(self.z_data),np.imag(self.z_data))
            l0s.set_data(self.f_data[self._fid]*1e-9,np.absolute(self.z_data_sim_norm[self._fid]))
            l1s.set_data(self.f_data[self._fid]*1e-9,np.angle(self.z_data_sim_norm[self._fid]))
            l2s.set_data(np.real(self.z_data_sim_norm[self._fid]),np.imag(self.z_data_sim_norm[self._fid]))
            fr_ann.set_text('fr = %e Hz +- %e Hz' % (self.fitresults['fr'],self.fitresults['fr_err']))
            Ql_ann.set_text('Ql = %e +- %e' % (self.fitresults['Ql'],self.fitresults['Ql_err']))
            Qc_ann.set_text('Qc = %e +- %e' % (self.fitresults['Qc'],self.fitresults['Qc_err']))
            Qi_ann.set_text('Qi = %e +- %e' % (self.fitresults['Qi'],self.fitresults['Qi_err']))
            fig.canvas.draw_idle()
        def btnclicked(event):
            self.autofit(electric_delay=None,fcrop=(sf1.val*1e9,sf2.val*1e9))
            self.__delay = self._delay
            sdelay.reset()
            update(event)
        sf1.on_changed(update)
        sf2.on_changed(update)
        sdelay.on_changed(update)
        btnax = plt.axes([0.05, 0.1, 0.1, 0.04])
        button = Button(btnax, 'auto-delay', color=axcolor, hovercolor='0.975')
        button.on_clicked(btnclicked)
        plt.show()	
        plt.close()

    def _S11_directrefl(self,f,fr=10e9,Ql=900,Qc=1000.,a=1.,alpha=0.,delay=.0):
        '''
        full model for notch type resonances
        '''
        phi = -self.phi
        #print(phi)
        complexQc = Qc*np.cos(phi)*np.exp(-1j*phi)
        return a*np.exp(1j*(alpha-2*np.pi*f*delay)) * (
            1. - 2.*Ql / (complexQc * 1 * (1. + 2j*Ql*(f/fr-1.)))
        )
        #return a*np.exp(np.complex(0,alpha))*np.exp(-2j*np.pi*f*delay) * ( 2.*Ql/complexQc - 1. + 2j*Ql*(fr-f)/fr ) / ( 1. - 2j*Ql*(fr-f)/fr )   

    def get_single_photon_limit(self,unit='dBm'):
        '''
        returns the amout of power in units of W necessary
        to maintain one photon on average in the cavity
        unit can be 'dbm' or 'watt'
        '''
        if self.fitresults!={}:
            fr = self.fitresults['fr']
            k_c = 2*np.pi*fr/self.fitresults['Qc']
            k_i = 2*np.pi*fr/self.fitresults['Qi']
            if unit=='dBm':
                return Watt2dBm(1./(4.*k_c/(2.*np.pi*hbar*fr*(k_c+k_i)**2)))
            elif unit=='watt':
                return 1./(4.*k_c/(2.*np.pi*hbar*fr*(k_c+k_i)**2))

        else:
            warnings.warn('Please perform the fit first',UserWarning)
            return None

    def get_photons_in_resonator(self,power,unit='dBm'):
        '''
        returns the average number of photons
        for a given power (defaul unit is 'dbm')
        unit can be 'dBm' or 'watt'
        '''
        if self.fitresults!={}:
            if unit=='dBm':
                power = dBm2Watt(power)
            fr = self.fitresults['fr']
            k_c = 2*np.pi*fr/self.fitresults['Qc']
            k_i = 2*np.pi*fr/self.fitresults['Qi']
            return 4.*k_c/(2.*np.pi*hbar*fr*(k_c+k_i)**2) * power
        else:
            warnings.warn('Please perform the fit first',UserWarning)
            return None

    ##############################
    # Added some stuff of myself #
    ##############################

    def coupling_C(self, Z_r, Z_0 = 50):
        Q_e = self.fitresults.get('Qc')
        Q_inter = self.fitresults.get('Qi')
        w_r = 2*np.pi*self.fitresults.get('fr')

        C_couple = np.sqrt(np.pi/(Z_0*Z_r*Q_e))*1/(w_r)
        # following Janvier's PhD thesis, critical coupling is when Q_i = Q_c 
        C_crit = np.sqrt(np.pi/(Z_0*Z_r*Q_inter))*1/(w_r)
        self.fitresults.update({
                        "C_crit": C_crit,
                        "C_couple": C_couple
        })
        
    def manual_fit_phase(self, f_data, z_data, delay=None, ignoreslope=True, guesses= None):
        """
        Fits the phase response of a strongly overcoupled (Qi >> Qc) resonator
        in reflection which corresponds to a circle centered around the origin
        (cf‌. phase_centered()).

        inputs:
        - z_data: Scattering data of which the phase should be fit. Data must be
                  distributed around origin ("circle-like").
        - guesses (opt.): If not given, initial guesses for the fit parameters
                          will be determined. If given, should contain useful
                          guesses for fit parameters as a tuple (fr, Ql, delay)

        outputs:
        - fr: Resonance frequency
        - Ql: Loaded quality factor
        - theta: Offset phase
        - delay: Time delay between output and input signal leading to linearly
                 frequency dependent phase shift
        """
        phase = np.unwrap(np.angle(z_data))
        
        # For centered circle roll-off should be close to 2pi. If not warn user.
        if np.max(phase) - np.min(phase) <= 0.8*2*np.pi:
            logging.warning(
                "Data does not cover a full circle (only {:.1f}".format(
                    np.max(phase) - np.min(phase)
                )
               +" rad). Increase the frequency span around the resonance?"
            )
            roll_off = np.max(phase) - np.min(phase)
        else:
            roll_off = 2*np.pi
        
        
        # Set useful starting parameters
        if guesses is None:
            # Use maximum of derivative of phase as guess for fr
            #phase_smooth = splrep(self.f_data, phase, k=5, s=100)
            #phase_derivative = splev(self.f_data, phase_smooth, der=1)
            phase_smooth = gaussian_filter1d(phase, 30)
            phase_derivative = np.gradient(phase_smooth)
            fr_guess = self.f_data[np.argmax(np.abs(phase_derivative))]
            Ql_guess = 2*fr_guess / (self.f_data[-1] - self.f_data[0])
            # Estimate delay from background slope of phase (substract roll-off)
            slope = phase[-1] - phase[0] + roll_off
            delay_guess = -slope / (2*np.pi*(self.f_data[-1]-self.f_data[0]))
        else:
            fr_guess, Ql_guess, delay_guess = guesses
        # This one seems stable and we do not need a manual guess for it
        theta_guess = 0.5*(np.mean(phase[:5]) + np.mean(phase[-5:]))
        
        # Fit model with less parameters first to improve stability of fit
        
        def residuals_Ql(params):
            Ql, = params
            return residuals_full((fr_guess, Ql, theta_guess, delay_guess))
        def residuals_fr_theta(params):
            fr, theta = params
            return residuals_full((fr, Ql_guess, theta, delay_guess))
        # def residuals_Ql_delay(params):
            # Ql, delay = params
            # return residuals_full((fr_guess, Ql, theta_guess, delay))
        def residuals_delay(params):
            delay, = params
            return residuals_full((fr_guess, Ql_guess, theta_guess, delay))
        def residuals_fr_Ql(params):
            fr, Ql = params
            return residuals_full((fr, Ql, theta_guess, delay_guess))
        # def residuals_fr(params):
            # fr, = params
            # return residuals_full((fr, Ql_guess, theta_guess, delay_guess))
        def residuals_full(params):
            return self._phase_dist(
                phase - self.phase_centered(self.f_data, *params)
            )

        p_final = spopt.leastsq(residuals_Ql, [Ql_guess])
        Ql_guess, = p_final[0]
        p_final = spopt.leastsq(residuals_fr_theta, [fr_guess, theta_guess])
        fr_guess, theta_guess = p_final[0]
        p_final = spopt.leastsq(residuals_delay, [delay_guess])
        delay_guess, = p_final[0]
        p_final = spopt.leastsq(residuals_fr_Ql, [fr_guess, Ql_guess])
        fr_guess, Ql_guess = p_final[0]
        # p_final = spopt.leastsq(residuals_fr, [fr_guess])
        # fr_guess, = p_final[0]
        # p_final = spopt.leastsq(residuals_Ql, [Ql_guess])
        # Ql_guess, = p_final[0]
        p_final = spopt.leastsq(residuals_full, [
            fr_guess, Ql_guess, theta_guess, delay_guess
        ])
        
        A1, A2, A3, A4, fr, Ql = self._fit_skewed_lorentzian(f_data,z_data)
        if self.df_error/fr > 0.0001 or self.dQl_error/Ql>0.1:
            print("WARNING: Calibration using Lorentz fit failed, trying phase fit...")
            A1 = np.mean(np.absolute(z_data))
            A2 = 0.
            A3 = 0.
            A4 = 0.
            #fr = np.mean(f_data)
            f = splrep(f_data,np.unwrap(np.angle(z_data)),k=5,s=self.phasefitsmooth)
            fr = f_data[np.argmax(np.absolute(splev(f_data,f,der=1)))]
            Ql = 1e4
        if ignoreslope==True:
            A2 = 0.
        else:
            A2 = 0.
            print("WARNING: The ignoreslope option is ignored! Corrections to the baseline should be done manually prior to fitting.")
            print("see also: resonator_tools.calibration.fit_baseline_amp() etc. for help on fitting the baseline.")
            print("There is also an example ipython notebook for using this function.")
            print("However, make sure to understand the impact of the baseline (parasitic coupled resonances etc.) on your system.")
            #z_data = (np.absolute(z_data)-A2*(f_data-fr)) * np.exp(np.angle(z_data)*1j)  #usually not necessary
        params = [A1, A2, A3, A4, fr, Ql]
     
        return p_final[0][3], params
    
    def _manual_fit_delay(self):
        """
        Finds the cable delay by repeatedly centering the "circle" and fitting
        the slope of the phase response.
        """
        
        # Translate data to origin
        xc, yc, r0 = self._fit_circle(self.z_data_raw)
        z_data = self.z_data_raw - complex(xc, yc)
        
        # Find first estimate of parameters
        fr, Ql, theta, self.delay = self._fit_phase(f_data, z_data)
        
        # Do not overreact (see end of for loop)
        self.delay *= 0.05
        
        # Iterate to improve result for delay
        for i in range(self.fit_delay_max_iterations):
            # Translate new best fit data to origin
            z_data = self.z_data_raw * np.exp(2j*np.pi*self.delay*self.f_data)
            xc, yc, r0 = self._fit_circle(z_data)
            z_data -= complex(xc, yc)
            
            # Find correction to current delay
            guesses = (fr, Ql, 5e-11)
            fr, Ql, theta, delay_corr = self._fit_phase(z_data, guesses)
            
            # Stop if correction would be smaller than "measurable"
            phase_fit = self.phase_centered(self.f_data, fr, Ql, theta, delay_corr)
            residuals = np.unwrap(np.angle(z_data)) - phase_fit
            if 2*np.pi*(self.f_data[-1]-self.f_data[0])*delay_corr <= np.std(residuals):
                break
            
            # Avoid overcorrection that makes procedure switch between positive
            # and negative delays
            if delay_corr*self.delay < 0: # different sign -> be careful
                if abs(delay_corr) > abs(self.delay):
                    self.delay *= 0.5
                else:
                    # delay += 0.1*delay_corr
                    self.delay += 0.1*np.sign(delay_corr)*5e-11
            else: # same direction -> can converge faster
                if abs(delay_corr) >= 1e-8:
                    self.delay += min(delay_corr, self.delay)
                elif abs(delay_corr) >= 1e-9:
                    self.delay *= 1.1
                else:
                    self.delay += delay_corr
        
        if 2*np.pi*(self.f_data[-1]-self.f_data[0])*delay_corr > np.std(residuals):
            logging.warning(
                "Delay could not be fit properly!"
            )
            
        
        # Store result in dictionary (also for backwards-compatibility)
        #self.fitresults["delay"] = self.delay
    
    def _manual_calibrate(self, f_data, z_data, ignoreslope=True,guessdelay=True,fixed_delay=None):
        """
        Finds the parameters for normalization of the scattering data. See
        Sij of port classes for explanation of parameters.
        """
        
        # Correct for delay and translate circle to origin
        self.delay, params = self.manual_fit_phase(f_data,z_data)
        z_data = self.z_data_raw * np.exp(2j*np.pi*self.delay*self.f_data)
        xc, yc, self.r0 = self._fit_circle(z_data)
        zc = complex(xc, yc)
        z_data -= zc
        
        # Find off-resonant point by fitting offset phase
        # (centered circle corresponds to lossless resonator in reflection)
        self.fr, self.Ql, theta, self.delay_remaining = self._fit_phase_x(z_data)
        self.theta = self._periodic_boundary(theta, np.pi)
        # beta = self._periodic_boundary(theta - np.pi)
        beta = self._periodic_boundary(theta+np.pi,np.pi)
        offrespoint = zc + self.r0*np.cos(beta) + 1j*self.r0*np.sin(beta)
        self.offrespoint = offrespoint
        #print(f"offresspoint = {offrespoint}")
        self.a = np.absolute(offrespoint)
        #self.alpha = np.angle(offrespoint)
        self.alpha = self._periodic_boundary(np.angle(offrespoint)+np.pi,np.pi)
        #print(f"alpha = {self.alpha}")
        self.phi = self._periodic_boundary(beta - self.alpha, np.pi)
        #print(f"phi = {self.phi}")
        # Store radius for later calculation
        self.r0 /= self.a
        #print(f"man calib: r0 = {self.r0}, zc = {zc}")
        return self.delay, self.a, self.alpha, self.fr, self.Ql, params[1], params[4]
    
    def _fit_phase_x(self, z_data, guesses=None):
        """
        Fits the phase response of a strongly overcoupled (Qi >> Qc) resonator
        in reflection which corresponds to a circle centered around the origin
        (cf‌. phase_centered()).

        inputs:
        - z_data: Scattering data of which the phase should be fit. Data must be
                  distributed around origin ("circle-like").
        - guesses (opt.): If not given, initial guesses for the fit parameters
                          will be determined. If given, should contain useful
                          guesses for fit parameters as a tuple (fr, Ql, delay)

        outputs:
        - fr: Resonance frequency
        - Ql: Loaded quality factor
        - theta: Offset phase
        - delay: Time delay between output and input signal leading to linearly
                 frequency dependent phase shift
        """
        phase = np.unwrap(np.angle(z_data))
        
        # For centered circle roll-off should be close to 2pi. If not warn user.
        if np.max(phase) - np.min(phase) <= 0.8*2*np.pi:
            logging.warning(
                "Data does not cover a full circle (only {:.1f}".format(
                    np.max(phase) - np.min(phase)
                )
               +" rad). Increase the frequency span around the resonance?"
            )
            roll_off = np.max(phase) - np.min(phase)
        else:
            roll_off = 2*np.pi
        
        # Set useful starting parameters
        if guesses is None:
            # Use maximum of derivative of phase as guess for fr
            #phase_smooth = splrep(self.f_data, phase, k=5, s=100)
            #phase_derivative = splev(self.f_data, phase_smooth, der=1)
            phase_smooth = gaussian_filter1d(phase, 30)
            phase_derivative = np.gradient(phase_smooth)
            fr_guess = self.f_data[np.argmax(np.abs(phase_derivative))]
            Ql_guess = 2*fr_guess / (self.f_data[-1] - self.f_data[0])
            # Estimate delay from background slope of phase (substract roll-off)
            slope = phase[-1] - phase[0] + roll_off
            delay_guess = -slope / (2*np.pi*(self.f_data[-1]-self.f_data[0]))
        else:
            fr_guess, Ql_guess, delay_guess = guesses
        # This one seems stable and we do not need ual guess for it
        theta_guess = 0.5*(np.mean(phase[:5]) + np.mean(phase[-5:]))
        
        # Fit model with less parameters first to improve stability of fit
        
        def residuals_Ql(params):
            Ql, = params
            return residuals_full((fr_guess, Ql, theta_guess, delay_guess))
        def residuals_fr_theta(params):
            fr, theta = params
            return residuals_full((fr, Ql_guess, theta, delay_guess))
        # def residuals_Ql_delay(params):
            # Ql, delay = params
            # return residuals_full((fr_guess, Ql, theta_guess, delay))
        def residuals_delay(params):
            delay, = params
            return residuals_full((fr_guess, Ql_guess, theta_guess, delay))
        def residuals_fr_Ql(params):
            fr, Ql = params
            return residuals_full((fr, Ql, theta_guess, delay_guess))
        # def residuals_fr(params):
            # fr, = params
            # return residuals_full((fr, Ql_guess, theta_guess, delay_guess))
        def residuals_full(params):
            return self._phase_dist(
                phase - self.phase_centered(self.f_data, *params)
            )

        p_final = spopt.leastsq(residuals_Ql, [Ql_guess])
        Ql_guess, = p_final[0]
        p_final = spopt.leastsq(residuals_fr_theta, [fr_guess, theta_guess])
        fr_guess, theta_guess = p_final[0]
        p_final = spopt.leastsq(residuals_delay, [delay_guess])
        delay_guess, = p_final[0]
        p_final = spopt.leastsq(residuals_fr_Ql, [fr_guess, Ql_guess])
        fr_guess, Ql_guess = p_final[0]
        # p_final = spopt.leastsq(residuals_fr, [fr_guess])
        # fr_guess, = p_final[0]
        # p_final = spopt.leastsq(residuals_Ql, [Ql_guess])
        # Ql_guess, = p_final[0]
        p_final = spopt.leastsq(residuals_full, [
            fr_guess, Ql_guess, theta_guess, delay_guess
        ])
        
        return p_final[0]

    
    
    def _phase_dist(self, angle):
        """
        Maps angle [-2pi, +2pi] to phase distance on circle [0, pi]
        """
        return np.pi - np.abs(np.pi - np.abs(angle))
    
    @classmethod
    def phase_centered(cls, f, fr, Ql, theta, delay=0.):
        """
        Yields the phase response of a strongly overcoupled (Qi >> Qc) resonator
        in reflection which corresponds to a circle centered around the origin.
        Additionally, a linear background slope is accounted for if needed.
        
        inputs:
        - fr: Resonance frequency
        - Ql: Loaded quality factor (and since Qi >> Qc also Ql = Qc)
        - theta: Offset phase
        - delay (opt.): Time delay between output and input signal leading to
                        linearly frequency dependent phase shift
        """
        return theta - 2*np.pi*delay*(f-fr) + 2.*np.arctan(2.*Ql*(1. - f/fr))
    ##############################
    ##############################
    ##############################


# class notch_port(circlefit, save_load, plotting, calibration):
#     '''
#     notch type port probed in transmission
#     '''
#     def __init__(self, f_data=None, z_data_raw=None):
#         self.porttype = 'notch'
#         self.fitresults = {}
#         self.z_data = None
#         if f_data is not None:
#             self.f_data = np.array(f_data)
#         else:
#             self.f_data=None
#         if z_data_raw is not None:
#             self.z_data_raw = np.array(z_data_raw)
#         else:
#             self.z_data_raw=None

#     def get_delay(self,f_data,z_data,delay=None,ignoreslope=True,guess=True):
#         '''
#         retrieves the cable delay assuming the ideal resonance has a circular shape
#         modifies the cable delay until the shape Im(S21) vs Re(S21) is circular
#         see "do_calibration"
#         '''
#         maxval = np.max(np.absolute(z_data))
#         z_data = z_data/maxval
#         A1, A2, A3, A4, fr, Ql = self._fit_skewed_lorentzian(f_data,z_data)
#         if ignoreslope==True:
#             A2 = 0.
#         else:
#             A2 = 0.
#             print("WARNING: The ignoreslope option is ignored! Corrections to the baseline should be done manually prior to fitting.")
#             print("see also: resonator_tools.calibration.fit_baseline_amp() etc. for help on fitting the baseline.")
#             print("There is also an example ipython notebook for using this function.")
#             print("However, make sure to understand the impact of the baseline (parasitic coupled resonances etc.) on your system.")
#             #z_data = (np.absolute(z_data)-A2*(f_data-fr)) * np.exp(np.angle(z_data)*1j)  #usually not necessary
#         if delay is None:
#             if guess==True:
#                 delay = self._guess_delay(f_data,z_data)
#             else:
#                 delay=0.
#             delay = self._fit_delay(f_data,z_data,delay,maxiter=400)
#         params = [A1, A2, A3, A4, fr, Ql]
#         return delay, params	

#     def do_calibration(self,f_data,z_data,ignoreslope=True,guessdelay=True,fixed_delay=None, Ql_guess=None, fr_guess=None):
#         '''
#         performs an automated calibration and tries to determine the prefactors a, alpha, delay
#         fr, Ql, and a possible slope are extra information, which can be used as start parameters for subsequent fits
#         see also "do_normalization"
#         the calibration procedure works for transmission line resonators as well
#         '''
#         delay, params = self.get_delay(f_data,z_data,ignoreslope=ignoreslope,guess=guessdelay,delay=fixed_delay)
#         z_data = (z_data-params[1]*(f_data-params[4]))*np.exp(2.*1j*np.pi*delay*f_data)
#         xc, yc, r0 = self._fit_circle(z_data)
#         zc = np.complex(xc,yc)
#         if Ql_guess is None: Ql_guess=np.absolute(params[5]) 
#         if fr_guess is None: fr_guess=params[4] 
#         fitparams = self._phase_fit(f_data,self._center(z_data,zc),0.,Ql_guess,fr_guess) 
#         theta, Ql, fr = fitparams
#         beta = self._periodic_boundary(theta+np.pi,np.pi)
#         offrespoint = np.complex((xc+r0*np.cos(beta)),(yc+r0*np.sin(beta)))
#         alpha = np.angle(offrespoint)
#         a = np.absolute(offrespoint)
#         return delay, a, alpha, fr, Ql, params[1], params[4]

#     def do_normalization(self,f_data,z_data,delay,amp_norm,alpha,A2,frcal):
#         '''
#         removes the prefactors a, alpha, delay and returns the calibrated data, see also "do_calibration"
#         works also for transmission line resonators
#         '''
#         #return (z_data-A2*(f_data-frcal))/amp_norm*np.exp(1j*(-alpha+2.*np.pi*delay*f_data))
#         return self.z_data_raw / self.a*np.exp( 1j*(-self.alpha + 2.*np.pi*self.delay*self.f_data))

#     def circlefit(self,f_data,z_data,fr=None,Ql=None,refine_results=False,calc_errors=True):
#         '''
#         performs a circle fit on a frequency vs. complex resonator scattering data set
#         Data has to be normalized!!
#         INPUT:
#         f_data,z_data: input data (frequency, complex S21 data)
#         OUTPUT:
#         outpus a dictionary {key:value} consisting of the fit values, errors and status information about the fit
#         values: {"phi0":phi0, "Ql":Ql, "absolute(Qc)":absQc, "Qi": Qi, "electronic_delay":delay, "complexQc":complQc, "resonance_freq":fr, "prefactor_a":a, "prefactor_alpha":alpha}
#         errors: {"phi0_err":phi0_err, "Ql_err":Ql_err, "absolute(Qc)_err":absQc_err, "Qi_err": Qi_err, "electronic_delay_err":delay_err, "resonance_freq_err":fr_err, "prefactor_a_err":a_err, "prefactor_alpha_err":alpha_err}
#         for details, see:
#             [1] (not diameter corrected) Jiansong Gao, "The Physics of Superconducting Microwave Resonators" (PhD Thesis), Appendix E, California Institute of Technology, (2008)
#             [2] (diameter corrected) M. S. Khalil, et. al., J. Appl. Phys. 111, 054510 (2012)
#             [3] (fitting techniques) N. CHERNOV AND C. LESORT, "Least Squares Fitting of Circles", Journal of Mathematical Imaging and Vision 23, 239, (2005)
#             [4] (further fitting techniques) P. J. Petersan, S. M. Anlage, J. Appl. Phys, 84, 3392 (1998)
#         the program fits the circle with the algebraic technique described in [3], the rest of the fitting is done with the scipy.optimize least square fitting toolbox
#         also, check out [5] S. Probst et al. "Efficient and reliable analysis of noisy complex scatterung resonator data for superconducting quantum circuits" (in preparation)
#         '''

#         if fr is None: fr=f_data[np.argmin(np.absolute(z_data))]
#         if Ql is None: Ql=1e6
#         xc, yc, r0 = self._fit_circle(z_data,refine_results=refine_results)
#         phi0 = -np.arcsin(yc/r0)
#         theta0 = self._periodic_boundary(phi0+np.pi,np.pi)
#         z_data_corr = self._center(z_data,np.complex(xc,yc))
#         theta0, Ql, fr = self._phase_fit(f_data,z_data_corr,theta0,Ql,fr)
#         #print("Ql from phasefit is: " + str(Ql))
#         absQc = Ql/(2.*r0)
#         complQc = absQc*np.exp(1j*((-1.)*phi0))
#         Qc = 1./(1./complQc).real	# here, taking the real part of (1/complQc) from diameter correction method
#         Qi_dia_corr = 1./(1./Ql-1./Qc)
#         Qi_no_corr = 1./(1./Ql-1./absQc)

#         results = {"Qi_dia_corr":Qi_dia_corr,"Qi_no_corr":Qi_no_corr,"absQc":absQc,"Qc_dia_corr":Qc,"Ql":Ql,"fr":fr,"theta0":theta0,"phi0":phi0}

#         #calculation of the error
#         p = [fr,absQc,Ql,phi0]
#         #chi_square, errors = rt.get_errors(rt.residuals_notch_ideal,f_data,z_data,p)
#         if calc_errors==True:
#             chi_square, cov = self._get_cov_fast_notch(f_data,z_data,p)
#             #chi_square, cov = rt.get_cov(rt.residuals_notch_ideal,f_data,z_data,p)

#             if cov is not None:
#                 errors = np.sqrt(np.diagonal(cov))
#                 fr_err,absQc_err,Ql_err,phi0_err = errors
#                 #calc Qi with error prop (sum the squares of the variances and covariaces)
#                 dQl = 1./((1./Ql-1./absQc)**2*Ql**2)
#                 dabsQc = - 1./((1./Ql-1./absQc)**2*absQc**2)
#                 Qi_no_corr_err = np.sqrt((dQl**2*cov[2][2]) + (dabsQc**2*cov[1][1])+(2*dQl*dabsQc*cov[2][1]))  #with correlations
#                 #calc Qi dia corr with error prop
#                 dQl = 1/((1/Ql-np.cos(phi0)/absQc)**2 *Ql**2)
#                 dabsQc = -np.cos(phi0)/((1/Ql-np.cos(phi0)/absQc)**2 *absQc**2)
#                 dphi0 = -np.sin(phi0)/((1/Ql-np.cos(phi0)/absQc)**2 *absQc)
#                 ##err1 = ( (dQl*cov[2][2])**2 + (dabsQc*cov[1][1])**2 + (dphi0*cov[3][3])**2 )
#                 err1 = ( (dQl**2*cov[2][2]) + (dabsQc**2*cov[1][1]) + (dphi0**2*cov[3][3]) )
#                 err2 = ( dQl*dabsQc*cov[2][1] + dQl*dphi0*cov[2][3] + dabsQc*dphi0*cov[1][3] )
#                 Qi_dia_corr_err =  np.sqrt(err1+2*err2)	 # including correlations
#                 errors = {"phi0_err":phi0_err, "Ql_err":Ql_err, "absQc_err":absQc_err, "fr_err":fr_err,"chi_square":chi_square,"Qi_no_corr_err":Qi_no_corr_err,"Qi_dia_corr_err": Qi_dia_corr_err}
#                 results.update( errors )
#             else:
#                 print("WARNING: Error calculation failed!")
#         else:
#             #just calc chisquared:
#             fun2 = lambda x: self._residuals_notch_ideal(x,f_data,z_data)**2
#             chi_square = 1./float(len(f_data)-len(p)) * (fun2(p)).sum()
#             errors = {"chi_square":chi_square}
#             results.update(errors)

#         return results

#     def autofit(self,electric_delay=None,fcrop=None,Ql_guess=None, fr_guess=None):
#         '''
#         automatic calibration and fitting
#         electric_delay: set the electric delay manually
#         fcrop = (f1,f2) : crop the frequency range used for fitting
#         '''
#         if fcrop is None:
#             self._fid = np.ones(self.f_data.size,dtype=bool)
#         else:
#             f1, f2 = fcrop
#             self._fid = np.logical_and(self.f_data>=f1,self.f_data<=f2)
#         delay, amp_norm, alpha, fr, Ql, A2, frcal =\
#                 self.do_calibration(self.f_data[self._fid],self.z_data_raw[self._fid],ignoreslope=True,guessdelay=True,fixed_delay=electric_delay,Ql_guess=Ql_guess, fr_guess=fr_guess)
#         self.z_data = self.do_normalization(self.f_data,self.z_data_raw,delay,amp_norm,alpha,A2,frcal)
#         self.fitresults = self.circlefit(self.f_data[self._fid],self.z_data[self._fid],fr,Ql,refine_results=False,calc_errors=True)
#         self.z_data_sim = A2*(self.f_data-frcal)+self._S21_notch(self.f_data,fr=self.fitresults["fr"],Ql=self.fitresults["Ql"],Qc=self.fitresults["absQc"],phi=self.fitresults["phi0"],a=amp_norm,alpha=alpha,delay=delay)
#         self.z_data_sim_norm = self._S21_notch(self.f_data,fr=self.fitresults["fr"],Ql=self.fitresults["Ql"],Qc=self.fitresults["absQc"],phi=self.fitresults["phi0"],a=1.0,alpha=0.,delay=0.)
#         self._delay = delay

#     def GUIfit(self):
#         '''
#         automatic fit with possible user interaction to crop the data and modify the electric delay
#         f1,f2,delay are determined in the GUI. Then, data is cropped and autofit with delay is performed
#         '''
#         #copy data
#         fmin, fmax = self.f_data.min(), self.f_data.max()
#         self.autofit()
#         self.__delay = self._delay
#         #prepare plot and slider
#         import matplotlib.pyplot as plt
#         from matplotlib.widgets import Slider, Button
#         fig, ((ax2,ax0),(ax1,ax3)) = plt.subplots(nrows=2,ncols=2)
#         plt.suptitle('Normalized data. Use the silders to improve the fitting if necessary.')
#         plt.subplots_adjust(left=0.25, bottom=0.25)
#         l0, = ax0.plot(self.f_data*1e-9,np.absolute(self.z_data))
#         l1, = ax1.plot(self.f_data*1e-9,np.angle(self.z_data))
#         l2, = ax2.plot(np.real(self.z_data),np.imag(self.z_data))
#         l0s, = ax0.plot(self.f_data*1e-9,np.absolute(self.z_data_sim_norm))
#         l1s, = ax1.plot(self.f_data*1e-9,np.angle(self.z_data_sim_norm))
#         l2s, = ax2.plot(np.real(self.z_data_sim_norm),np.imag(self.z_data_sim_norm))
#         ax0.set_xlabel('f (GHz)')
#         ax1.set_xlabel('f (GHz)')
#         ax2.set_xlabel('real')
#         ax0.set_ylabel('amp')
#         ax1.set_ylabel('phase (rad)')
#         ax2.set_ylabel('imagl')
#         fr_ann = ax3.annotate('fr = %e Hz +- %e Hz' % (self.fitresults['fr'],self.fitresults['fr_err']),xy=(0.1, 0.8), xycoords='axes fraction')
#         Ql_ann = ax3.annotate('Ql = %e +- %e' % (self.fitresults['Ql'],self.fitresults['Ql_err']),xy=(0.1, 0.6), xycoords='axes fraction')
#         Qc_ann = ax3.annotate('Qc = %e +- %e' % (self.fitresults['absQc'],self.fitresults['absQc_err']),xy=(0.1, 0.4), xycoords='axes fraction')
#         Qi_ann = ax3.annotate('Qi = %e +- %e' % (self.fitresults['Qi_dia_corr'],self.fitresults['Qi_dia_corr_err']),xy=(0.1, 0.2), xycoords='axes fraction')
#         axcolor = 'lightgoldenrodyellow'
#         axdelay = plt.axes([0.25, 0.05, 0.65, 0.03], facecolor=axcolor)
#         axf2 = plt.axes([0.25, 0.1, 0.65, 0.03], facecolor=axcolor)
#         axf1 = plt.axes([0.25, 0.15, 0.65, 0.03], facecolor=axcolor)
#         sscale = 10.
#         sdelay = Slider(axdelay, 'delay', -1., 1., valinit=self.__delay/(sscale*self.__delay),valfmt='%f')
#         df = (fmax-fmin)*0.05
#         sf2 = Slider(axf2, 'f2', (fmin-df)*1e-9, (fmax+df)*1e-9, valinit=fmax*1e-9,valfmt='%.10f GHz')
#         sf1 = Slider(axf1, 'f1', (fmin-df)*1e-9, (fmax+df)*1e-9, valinit=fmin*1e-9,valfmt='%.10f GHz')
#         def update(val):
#             self.autofit(electric_delay=sdelay.val*sscale*self.__delay,fcrop=(sf1.val*1e9,sf2.val*1e9))
#             l0.set_data(self.f_data*1e-9,np.absolute(self.z_data))
#             l1.set_data(self.f_data*1e-9,np.angle(self.z_data))
#             l2.set_data(np.real(self.z_data),np.imag(self.z_data))
#             l0s.set_data(self.f_data[self._fid]*1e-9,np.absolute(self.z_data_sim_norm[self._fid]))
#             l1s.set_data(self.f_data[self._fid]*1e-9,np.angle(self.z_data_sim_norm[self._fid]))
#             l2s.set_data(np.real(self.z_data_sim_norm[self._fid]),np.imag(self.z_data_sim_norm[self._fid]))
#             fr_ann.set_text('fr = %e Hz +- %e Hz' % (self.fitresults['fr'],self.fitresults['fr_err']))
#             Ql_ann.set_text('Ql = %e +- %e' % (self.fitresults['Ql'],self.fitresults['Ql_err']))
#             Qc_ann.set_text('|Qc| = %e +- %e' % (self.fitresults['absQc'],self.fitresults['absQc_err']))
#             Qi_ann.set_text('Qi_dia_corr = %e +- %e' % (self.fitresults['Qi_dia_corr'],self.fitresults['Qi_dia_corr_err']))
#             fig.canvas.draw_idle()
#         def btnclicked(event):
#             self.autofit(electric_delay=None,fcrop=(sf1.val*1e9,sf2.val*1e9))
#             self.__delay = self._delay
#             sdelay.reset()
#             update(event)
#         sf1.on_changed(update)
#         sf2.on_changed(update)
#         sdelay.on_changed(update)
#         btnax = plt.axes([0.05, 0.1, 0.1, 0.04])
#         button = Button(btnax, 'auto-delay', color=axcolor, hovercolor='0.975')
#         button.on_clicked(btnclicked)
#         plt.show()	
#         plt.close()

#     def _S21_notch(self,f,fr=10e9,Ql=900,Qc=1000.,phi=0.,a=1.,alpha=0.,delay=.0):
#         '''
#         full model for notch type resonances
#         '''
#         return a*np.exp(np.complex(0,alpha))*np.exp(-2j*np.pi*f*delay)*(1.-Ql/Qc*np.exp(1j*phi)/(1.+2j*Ql*(f-fr)/fr))	 

#     def get_single_photon_limit(self,unit='dBm',diacorr=True):
#         '''
#         returns the amout of power in units of W necessary
#         to maintain one photon on average in the cavity
#         unit can be 'dBm' or 'watt'
#         '''
#         if self.fitresults!={}:
#             fr = self.fitresults['fr']
#             if diacorr:
#                 k_c = 2*np.pi*fr/self.fitresults['Qc_dia_corr']
#                 k_i = 2*np.pi*fr/self.fitresults['Qi_dia_corr']
#             else:
#                 k_c = 2*np.pi*fr/self.fitresults['absQc']
#                 k_i = 2*np.pi*fr/self.fitresults['Qi_no_corr']
#             if unit=='dBm':
#                 return Watt2dBm(1./(4.*k_c/(2.*np.pi*hbar*fr*(k_c+k_i)**2)))
#             elif unit=='watt':
#                 return 1./(4.*k_c/(2.*np.pi*hbar*fr*(k_c+k_i)**2))				  
#         else:
#             warnings.warn('Please perform the fit first',UserWarning)
#             return None

#     def get_photons_in_resonator(self,power,unit='dBm',diacorr=True):
#         '''
#         returns the average number of photons
#         for a given power in units of W
#         unit can be 'dBm' or 'watt'
#         '''
#         if self.fitresults!={}:
#             if unit=='dBm':
#                 power = dBm2Watt(power)
#             fr = self.fitresults['fr']
#             if diacorr:
#                 k_c = 2*np.pi*fr/self.fitresults['Qc_dia_corr']
#                 k_i = 2*np.pi*fr/self.fitresults['Qi_dia_corr']
#             else:
#                 k_c = 2*np.pi*fr/self.fitresults['absQc']
#                 k_i = 2*np.pi*fr/self.fitresults['Qi_no_corr']
#             return 4.*k_c/(2.*np.pi*hbar*fr*(k_c+k_i)**2) * power
#         else:
#             warnings.warn('Please perform the fit first',UserWarning)
#             return None	  

#     ##############################
#     # Added some stuff of myself #
#     ##############################

#     def coupling_C(self, Z_r, Z_0 = 50):
#         Q_e = self.fitresults.get('Qc')
#         Q_inter = self.fitresults.get('Qi')
#         w_r = 2*np.pi*self.fitresults.get('fr')

#         C_couple = np.sqrt(np.pi/(Z_0*Z_r*Q_e))*1/(w_r)
#         # following Janvier's PhD thesis, critical coupling is when Q_i = Q_c 
#         C_crit = np.sqrt(np.pi/(Z_0*Z_r*Q_inter))*1/(w_r)
#         self.fitresults.update({
#                         "C_crit": C_crit,
#                         "C_couple": C_couple
#         })

#     ##############################
#     ##############################
#     ##############################
class transmission_port(circlefit,save_load,plotting):
    '''
    a class for handling transmission measurements
    '''

    def __init__(self,f_data=None,z_data_raw=None):
        self.porttype = 'transm'
        self.fitresults = {}
        if f_data is not None:
            self.f_data = np.array(f_data)
        else:
            self.f_data=None
        if z_data_raw is not None:
            self.z_data_raw = np.array(z_data_raw)
        else:
            self.z_data=None

    def _S21(self,f,fr,Ql,A):
        return A**2/(1.+4.*Ql**2*((f-fr)/fr)**2) 

    def fit(self):
        self.ampsqr = (np.absolute(self.z_data_raw))**2
        p = [self.f_data[np.argmax(self.ampsqr)],1000.,np.amax(self.ampsqr)]
        popt, pcov = spopt.curve_fit(self._S21, self.f_data, self.ampsqr,p)
        errors = np.sqrt(np.diag(pcov))
        self.fitresults = {'fr':popt[0],'fr_err':errors[0],'Ql':popt[1],'Ql_err':errors[1],'Ampsqr':popt[2],'Ampsqr_err':errors[2]} 

class resonator(object):
    '''
    Universal resonator analysis class
    It can handle different kinds of ports and assymetric resonators.
    '''
    def __init__(self, ports = {}, comment = None):
        '''
        initializes the resonator class object
        ports (dictionary {key:value}): specify the name and properties of the coupling ports
            e.g. ports = {'1':'direct', '2':'notch'}
        comment: add a comment
        '''
        self.comment = comment
        self.port = {}
        self.transm = {}
        if len(ports) > 0:
            for key, pname in iter(ports.items()):
                if pname=='direct':
                    self.port.update({key:reflection_port()})
                elif pname=='notch':
                    self.port.update({key:notch_port()})
                else:
                    warnings.warn("Undefined input type! Use 'direct' or 'notch'.", SyntaxWarning)
        if len(self.port) == 0: warnings.warn("Resonator has no coupling ports!", UserWarning)

    def add_port(self,key,pname):
        if pname=='direct':
            self.port.update({key:reflection_port()})
        elif pname=='notch':
            self.port.update({key:notch_port()})
        else:
            warnings.warn("Undefined input type! Use 'direct' or 'notch'.", SyntaxWarning)
        if len(self.port) == 0: warnings.warn("Resonator has no coupling ports!", UserWarning)

    def delete_port(self,key):
        del self.port[key]
        if len(self.port) == 0: warnings.warn("Resonator has no coupling ports!", UserWarning)

    def get_Qi(self):
        '''
        based on the number of ports and the corresponding measurements
        it calculates the internal losses
        '''
        pass

    def get_single_photon_limit(self,port):
        '''
        returns the amout of power necessary to maintain one photon 
        on average in the cavity
        '''
        pass

    def get_photons_in_resonator(self,power,port):
        '''
        returns the average number of photons
        for a given power
        '''
        pass

    def add_transm_meas(self,port1, port2):
        '''
        input: port1
        output: port2
        adds a transmission measurement 
        connecting two direct ports S21
        '''
        key = port1 + " -> " + port2
        self.port.update({key:transm()})
        pass

class batch_processing(object):
    '''
    A class for batch processing of resonator data as a function of another variable
    Typical applications are power scans, magnetic field scans etc.
    '''

    def __init__(self,porttype):
        '''
        porttype = 'notch', 'direct', 'transm'
        results is an array of dictionaries containing the fitresults
        '''
        self.porttype = porttype
        self.results = []

    def autofit(self,cal_dataslice = 0):
        '''
        fits all data
        cal_dataslice: choose scatteringdata which should be used for calibration
        of the amplitude and phase, default = 0 (first)
        '''
        pass

class coupled_resonators(batch_processing):
    '''
    A class for fitting a resonator coupled to a second one
    '''

    def __init__(self,porttype):
        self.porttype = porttype
        self.results = []

#def GUIfit(porttype,f_data,z_data_raw):
#	'''
#	GUI based fitting process enabeling cutting the data and manually setting the delay
#	It employs the Matplotlib widgets
#	return f1, f2 and delay, which should be employed for the real fitting
#	'''
#	if porttype=='direct':
#		p = reflection_port(f_data=f_data,z_data_raw=z_data_raw)
#	elif porttype =='notch':
#		p = notch_port(f_data=f_data,z_data_raw=z_data_raw)
#	else:
#		warnings.warn('Not supported!')
#		return None
#	import matplotlib.pyplot as plt
#	from matplotlib.widgets import Slider, Button, RadioButtons
#	#plt.style.use('ggplot')
#	fig, axes = plt.subplots(nrows=2,ncols=2)
#	
#	return f1,f2,delay