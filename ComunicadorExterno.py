# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import random
import uuid
import datetime

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
port = 9011

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

ComunicadorExterno = Agent('ComunicadorExterno',
                       agn.ComunicadorExterno,
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
    """
    Entrypoint de comunicacion
    """
    global mss_cnt
    logging.info("ARRIBA?")
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Enviar_Peticion':
        return recibir_peticion(req, content)
    
def recibir_peticion(req, content):
    global mss_cnt
    mss_cnt = mss_cnt + 1
    logging.info('Peticion recibida')
    nombre_tienda = str(req.value(content, agn.nombre_tienda))
    logging.info('nombre_tienda: ' + nombre_tienda)
    nombre = str(req.value(content, agn.nombre))
    logging.info('nombre: ' + nombre)
    precio = str(req.value(content, agn.precio))
    logging.info('precio: ' + precio)
    peso = str(req.value(content, agn.peso))
    logging.info('peso: ' + peso)
    marca = str(req.value(content, agn.tieneMarca))
    logging.info('marca: ' + marca)
    tipo = str(req.value(content, agn.tipo))
    logging.info('tipo: ' + tipo)
    cuenta_bancaria = str(req.value(content, agn.cuenta_bancaria))
    logging.info('cuenta_bancaria: ' + cuenta_bancaria)

    productos = Graph().parse('./data/product.owl')
    sparql_query = Template('''
        SELECT ?producto ?nombre
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto pontp:nombre ?nombre .
            FILTER (
                ?nombre = '$nombre' 
            )
        }
    ''').substitute(dict(
        nombre = nombre
    ))
    result = productos.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            pontp=Namespace("http://www.products.org/ontology/property/")
        )
    )
    for x in result:
        if((str(x.nombre) == str(nombre))):
            return rechazar_pedido()
    rechazar = int(random.uniform(1, 100))
    if rechazar < 75:
        return aceptar_pedido(nombre, nombre_tienda, peso, precio, marca, tipo)
    else:
        return rechazar_pedido()

    return Graph().serialize(format='xml')

def aceptar_pedido(nombre, nombre_tienda, peso, precio, marca, tipo):
    global mss_cnt
    mss_cnt = mss_cnt + 1
    respuesta = "Producto aceptado"
    gRespuestaPeticion = Graph()
    RespuestaPeticion = agn['RespuestaPeticion' + str(mss_cnt)]
    gRespuestaPeticion.add((RespuestaPeticion, RDF.type, Literal('RespuestaPeticion')))
    gRespuestaPeticion.add((RespuestaPeticion, agn.respuesta_peticion, Literal(respuesta)))
    return gRespuestaPeticion.serialize(format = 'xml')

def rechazar_pedido():
    global mss_cnt
    mss_cnt = mss_cnt + 1
    respuesta = "Producto no aceptado"
    gRespuestaPeticion = Graph()
    RespuestaPeticion = agn['RespuestaPeticion' + str(mss_cnt)]
    gRespuestaPeticion.add((RespuestaPeticion, RDF.type, Literal('RespuestaPeticion')))
    gRespuestaPeticion.add((RespuestaPeticion, agn.respuesta_peticion, Literal(respuesta)))
    return gRespuestaPeticion.serialize(format = 'xml')



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
    ComunicadorExterno.register_agent(DirectoryAgent)
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