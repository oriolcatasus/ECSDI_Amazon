# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import uuid

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests

import logging
logging.basicConfig(level=logging.DEBUG)

import Constants.Constants as Constants


# Configuration stuff
hostname = '127.0.1.1'
port = 9009

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteExtEntidadBancaria = Agent('AgenteExtEntidadBancaria',
                       agn.AgenteExtEntidadBancaria,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/comm")
def comunicacion():
    global dsgraph
    global mss_cnt
  
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'CobrarP':        
        return cobrarP(req, content)
    elif accion == 'Pagar':
        return pagar(req, content)
    elif accion == 'PagarTiendaExterna':
        return pagarTiendaExterna(req, content)

def cobrarP(req, content):
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    tarjeta_bancaria = req.value(content, agn.tarjeta_bancaria)
    precio_total = req.value(content, agn.precio_total)
    logging.info("Se ha realizado el cobro en la tarjeta bancaria " + str(tarjeta_bancaria) +
                " de un importe de " + str(precio_total)+ "€")
    respuesta = str("Cobro realizado correctamente")
    gCobroRealizado = Graph()
    cobroRealizado = agn['cobroRealizado_' + str(mss_cnt)]
    gCobroRealizado.add((cobroRealizado, RDF.type, Literal('CobroRealizado')))
    gCobroRealizado.add((cobroRealizado, agn.respuesta, Literal(respuesta)))
    return gCobroRealizado.serialize(format='xml')

def pagar(req, content):
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    tarjeta_bancaria = req.value(content, agn.tarjeta_bancaria)
    precio_total = req.value(content, agn.precio_total)
    logging.info("Se ha realizado el pago a la tarjeta bancaria " + str(tarjeta_bancaria) +
                " de un importe de " + str(precio_total)+ "€")
    respuesta = str("Pago realizado correctamente")
    gCobroRealizado = Graph()
    cobroRealizado = agn['pagoRealizado_' + str(mss_cnt)]
    gCobroRealizado.add((cobroRealizado, RDF.type, Literal('PagoRealizado')))
    gCobroRealizado.add((cobroRealizado, agn.respuesta, Literal(respuesta)))
    return gCobroRealizado.serialize(format='xml')

def pagarTiendaExterna(req, content):
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    cuenta_bancaria = req.value(content, agn.cuenta_bancaria)
    precio = req.value(content, agn.precio)
    nombreProd = req.value(content, agn.nombre_prod)
    logging.info("Se ha realizado el pago del producto externo " + str(nombreProd) +
    "a la cuenta bancaria " + str(cuenta_bancaria) + " de un importe de " + str(precio) + "€")
    respuesta = str("Pago realizado correctamente")
    gCobroRealizado = Graph()
    cobroRealizado = agn['pagoRealizado_' + str(mss_cnt)]
    gCobroRealizado.add((cobroRealizado, RDF.type, Literal('PagoRealizado')))
    gCobroRealizado.add((cobroRealizado, agn.respuesta, Literal(respuesta)))
    return gCobroRealizado.serialize(format='xml')


@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    AgenteExtEntidadBancaria.register_agent(DirectoryAgent)
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')



