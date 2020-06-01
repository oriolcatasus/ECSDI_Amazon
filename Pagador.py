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
port = 9008

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

Pagador = Agent('Pagador',
                       agn.Pagador,
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
    if accion == 'Cobrar':        
        return cobrar(req, content)
    elif accion == 'Pagar':
        return pagar(req, content)
    elif accion == 'PagarTiendaExterna':
        return pagarTiendaExterna(req, content)

def cobrar(req, content):
    global mss_cnt

    mss_cnt = mss_cnt + 1
    logging.info("Se empezará a cobrar el pedido")
    tarjeta_bancaria = req.value(content, agn.tarjeta_bancaria)
    precio_total = req.value(content, agn.precio_total)
    AgenteExtEntidadBancaria = Pagador.directory_search(DirectoryAgent, agn.AgenteExtEntidadBancaria)
    gCobrarP = Graph()
    cobrarP = agn['cobrarP_' + str(mss_cnt)]
    gCobrarP.add((cobrarP, RDF.type, Literal('CobrarP')))
    gCobrarP.add((cobrarP, agn.tarjeta_bancaria, Literal(tarjeta_bancaria)))
    gCobrarP.add((cobrarP, agn.precio_total, Literal(precio_total)))
    message = build_message(
        gCobrarP,
        perf=Literal('request'),
        sender=Pagador.uri,
        receiver=AgenteExtEntidadBancaria.uri,
        msgcnt=mss_cnt,
        content=cobrarP
    )
    response = send_message(message, AgenteExtEntidadBancaria.address)
    respuesta_cobro = ""
    for item in response.subjects(RDF.type, Literal('CobroRealizado')):
        for cobroRelalizado in response.objects(item, agn.respuesta):
            respuesta_cobro = str(cobroRelalizado)
            logging.info(respuesta_cobro)
    gRespuestaCobro = Graph()
    RespuestaCobro = agn['RespuestaCobro_' + str(mss_cnt)]
    gRespuestaCobro.add((RespuestaCobro, RDF.type, Literal('RespuestaCobro')))
    gRespuestaCobro.add((RespuestaCobro, agn.respuesta_cobro, Literal(respuesta_cobro)))
    return gRespuestaCobro.serialize(format='xml')

def pagar(req, content):
    global mss_cnt

    mss_cnt = mss_cnt + 1
    logging.info("Se empezará a realizar el pago")
    tarjeta_bancaria = req.value(content, agn.tarjeta_bancaria)
    precio_total = req.value(content, agn.precio_total)
    AgenteExtEntidadBancaria = Pagador.directory_search(DirectoryAgent, agn.AgenteExtEntidadBancaria)
    gCobrarP = Graph()
    cobrarP = agn['pagar_' + str(mss_cnt)]
    gCobrarP.add((cobrarP, RDF.type, Literal('Pagar')))
    gCobrarP.add((cobrarP, agn.tarjeta_bancaria, Literal(tarjeta_bancaria)))
    gCobrarP.add((cobrarP, agn.precio_total, Literal(precio_total)))
    message = build_message(
        gCobrarP,
        perf=Literal('request'),
        sender=Pagador.uri,
        receiver=AgenteExtEntidadBancaria.uri,
        msgcnt=mss_cnt,
        content=cobrarP
    )
    response = send_message(message, AgenteExtEntidadBancaria.address)
    respuesta_cobro = ""
    for item in response.subjects(RDF.type, Literal('PagoRealizado')):
        for cobroRelalizado in response.objects(item, agn.respuesta):
            respuesta_cobro = str(cobroRelalizado)
            logging.info(respuesta_cobro)
    gRespuestaCobro = Graph()
    RespuestaCobro = agn['RespuestaPago' + str(mss_cnt)]
    gRespuestaCobro.add((RespuestaCobro, RDF.type, Literal('RespuestaPago')))
    gRespuestaCobro.add((RespuestaCobro, agn.respuesta_cobro, Literal(respuesta_cobro)))
    return gRespuestaCobro.serialize(format='xml')

def pagarTiendaExterna(req, content):
    global mss_cnt

    mss_cnt = mss_cnt + 1
    logging.info("Se empezará a realizar el pago a la tienda externa")
    cuenta_bancaria = req.value(content, agn.cuenta_bancaria)
    precio = req.value(content, agn.precio)
    nombreProd = req.value(content, agn.nombre_prod)
    AgenteExtEntidadBancaria = Pagador.directory_search(DirectoryAgent, agn.AgenteExtEntidadBancaria)
    gCobrarP = Graph()
    cobrarP = agn['pagar_tienda_externa' + str(mss_cnt)]
    gCobrarP.add((cobrarP, RDF.type, Literal('PagarTiendaExterna')))
    gCobrarP.add((cobrarP, agn.cuenta_bancaria, Literal(cuenta_bancaria)))
    gCobrarP.add((cobrarP, agn.precio, Literal(precio)))
    gCobrarP.add((cobrarP, agn.nombre_prod, Literal(nombreProd)))
    message = build_message(
        gCobrarP,
        perf=Literal('request'),
        sender=Pagador.uri,
        receiver=AgenteExtEntidadBancaria.uri,
        msgcnt=mss_cnt,
        content=cobrarP
    )
    response = send_message(message, AgenteExtEntidadBancaria.address)
    respuesta_cobro = ""
    for item in response.subjects(RDF.type, Literal('PagoRealizado')):
        for cobroRelalizado in response.objects(item, agn.respuesta):
            respuesta_cobro = str(cobroRelalizado)
            logging.info(respuesta_cobro)
    gRespuestaCobro = Graph()
    RespuestaCobro = agn['RespuestaPago' + str(mss_cnt)]
    gRespuestaCobro.add((RespuestaCobro, RDF.type, Literal('RespuestaPago')))
    gRespuestaCobro.add((RespuestaCobro, agn.respuesta_cobro, Literal(respuesta_cobro)))
    return gRespuestaCobro.serialize(format='xml')





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
    Pagador.register_agent(DirectoryAgent)
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

